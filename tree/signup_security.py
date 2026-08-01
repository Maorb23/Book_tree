import hashlib
import ipaddress
import logging

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


logger = logging.getLogger(__name__)


class RateLimitReservation:
    def __init__(self, key, allowed):
        self.key = key
        self.allowed = allowed
        self._active = allowed

    def commit(self):
        self._active = False

    def rollback(self):
        if not self._active:
            return
        try:
            remaining = cache.decr(self.key)
            if remaining <= 0:
                cache.delete(self.key)
        except ValueError:
            pass
        self._active = False


def get_client_ip(request):
    """Return a validated client IP without trusting arbitrary forwarding headers."""
    candidates = []
    if settings.TRUST_RAILWAY_PROXY_HEADERS:
        candidates.append(request.META.get('HTTP_X_REAL_IP'))
    candidates.append(request.META.get('REMOTE_ADDR'))

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return ipaddress.ip_address(candidate.strip()).compressed
        except ValueError:
            continue
    return 'unknown'


def rate_limit_key(limit_type, identity):
    identity_hash = hashlib.sha256(identity.encode('utf-8')).hexdigest()
    return f'auth_rate_limit:{limit_type}:{identity_hash}'


def acquire_rate_limit(limit_type, identity, limit):
    """Atomically reserve one fixed-window counter slot."""
    key = rate_limit_key(limit_type, identity)
    window = settings.AUTH_RATE_LIMIT_WINDOW_SECONDS

    if cache.add(key, 1, timeout=window):
        return RateLimitReservation(key, True)

    try:
        count = cache.incr(key)
    except ValueError:
        # The key can expire between add() and incr(); retry once as a new window.
        allowed = cache.add(key, 1, timeout=window)
        return RateLimitReservation(key, allowed)

    if count <= limit:
        return RateLimitReservation(key, True)

    # A blocked request must not push the stored counter beyond its configured cap.
    try:
        cache.decr(key)
    except ValueError:
        pass
    return RateLimitReservation(key, False)


def log_rate_limit(limit_type, client_ip=None, email=None):
    email_hash = None
    if email:
        email_hash = hashlib.sha256(email.encode('utf-8')).hexdigest()[:12]
    logger.warning(
        'signup_security event=rate_limit_blocked type=%s client_ip=%s email_hash=%s timestamp=%s',
        limit_type,
        client_ip or '-',
        email_hash or '-',
        timezone.now().isoformat(),
    )


def verify_turnstile(token, client_ip):
    if not token:
        _log_turnstile('missing', client_ip)
        return False
    if len(token) > 2048:
        _log_turnstile('invalid-token-format', client_ip)
        return False
    if not settings.TURNSTILE_SECRET_KEY:
        _log_turnstile('server-misconfigured', client_ip)
        return False

    try:
        response = requests.post(
            settings.TURNSTILE_SITEVERIFY_URL,
            data={
                'secret': settings.TURNSTILE_SECRET_KEY,
                'response': token,
                'remoteip': client_ip,
            },
            timeout=settings.TURNSTILE_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError):
        _log_turnstile('siteverify-error', client_ip)
        return False

    if not isinstance(result, dict) or result.get('success') is not True:
        codes = result.get('error-codes') if isinstance(result, dict) else None
        category = _turnstile_failure_category(codes)
        _log_turnstile(category, client_ip)
        return False

    if result.get('action') != 'signup':
        _log_turnstile('action-mismatch', client_ip)
        return False

    _log_turnstile('success', client_ip, level=logging.INFO)
    return True


def _turnstile_failure_category(error_codes):
    safe_categories = {
        'missing-input-secret',
        'invalid-input-secret',
        'missing-input-response',
        'invalid-input-response',
        'bad-request',
        'timeout-or-duplicate',
        'internal-error',
    }
    if not isinstance(error_codes, list):
        return 'invalid-response'
    known = sorted({code for code in error_codes if code in safe_categories})
    return ','.join(known) if known else 'verification-failed'


def _log_turnstile(category, client_ip, level=logging.WARNING):
    logger.log(
        level,
        'signup_security event=turnstile category=%s client_ip=%s timestamp=%s',
        category,
        client_ip,
        timezone.now().isoformat(),
    )
