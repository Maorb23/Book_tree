"""
Django settings for book_tree project.
"""
import os
from pathlib import Path
from email.utils import formataddr, parseaddr
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-book-tree-dev-key-change-in-production')


def _env(name, default=''):
    return os.getenv(name, default).strip()


def _bool_env(name, default='false'):
    return _env(name, default).lower() in ('1', 'true', 'yes', 'on')


def _int_env(name, default):
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _csv_env(name, default=''):
    return [item.strip() for item in os.getenv(name, default).split(',') if item.strip()]


def _email_env(name, default):
    value = _env(name, default)
    value = value.replace('<<', '<').replace('>>', '>')
    parts = value.rsplit(maxsplit=1)
    if len(parts) == 2 and '@' in parts[1]:
        return formataddr((parts[0], parts[1].strip('<>')))

    display_name, address = parseaddr(value)
    if address and display_name:
        return formataddr((display_name, address))
    if address and not any(ch.isspace() for ch in address):
        return address
    return value


def _normalize_csrf_origin(value):
    origin = value.strip().rstrip('/')
    if not origin:
        return ''
    if origin.startswith('.'):
        origin = f'*.{origin.lstrip(".")}'
    if not origin.startswith(('http://', 'https://')):
        origin = f'https://{origin}'
    return origin


DEBUG = _bool_env('DEBUG', 'true')

railway_public_domain = _env('RAILWAY_PUBLIC_DOMAIN')

if _env('ALLOWED_HOSTS'):
    ALLOWED_HOSTS = _csv_env('ALLOWED_HOSTS')
else:
    ALLOWED_HOSTS = ['*']
if railway_public_domain and railway_public_domain not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(railway_public_domain)

CSRF_TRUSTED_ORIGINS = [
    origin for origin in (
        _normalize_csrf_origin(value)
        for value in _csv_env('CSRF_TRUSTED_ORIGINS')
    )
    if origin
]
if railway_public_domain:
    railway_origin = _normalize_csrf_origin(railway_public_domain)
    if railway_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(railway_origin)

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'tree',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'book_tree.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'book_tree.wsgi.application'

DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    parsed = urlparse(DATABASE_URL)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': parsed.path.lstrip('/'),
            'USER': parsed.username,
            'PASSWORD': parsed.password,
            'HOST': parsed.hostname,
            'PORT': parsed.port or '',
            'CONN_MAX_AGE': _int_env('DB_CONN_MAX_AGE', 60),
            'OPTIONS': {'sslmode': 'require'} if _bool_env('DB_SSL', 'true') else {},
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOW_ALL_ORIGINS = _bool_env('CORS_ALLOW_ALL_ORIGINS', 'true')

RESEND_API_KEY = _env('RESEND_API_KEY')
RESEND_API_URL = _env('RESEND_API_URL', 'https://api.resend.com/emails')
RESEND_TIMEOUT = _int_env('RESEND_TIMEOUT', 10)
GOOGLE_BOOKS_API_KEY = _env('GOOGLE_BOOKS_API_KEY')
NYTIMES_BOOKS_API_KEY = _env('NYTIMES_BOOKS_API_KEY')
NYTIMES_ARTICLE_SEARCH_API_KEY = _env('NYTIMES_ARTICLE_SEARCH_API_KEY', NYTIMES_BOOKS_API_KEY)
GUARDIAN_API_KEY = _env('GUARDIAN_API_KEY')
EMAIL_PROVIDER = _env('EMAIL_PROVIDER', 'resend' if RESEND_API_KEY else '').lower()
EMAIL_BACKEND = (
    'tree.email_backends.ResendEmailBackend'
    if EMAIL_PROVIDER == 'resend'
    else _env('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
)
EMAIL_HOST = _env('EMAIL_HOST')
EMAIL_PORT = _int_env('EMAIL_PORT', 587)
EMAIL_HOST_USER = _env('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = _env('EMAIL_HOST_PASSWORD')
EMAIL_USE_SSL = _bool_env('EMAIL_USE_SSL', 'false')
EMAIL_USE_TLS = _bool_env('EMAIL_USE_TLS', 'true') and not EMAIL_USE_SSL
EMAIL_TIMEOUT = _int_env('EMAIL_TIMEOUT', 10)
DEFAULT_FROM_EMAIL = _email_env('DEFAULT_FROM_EMAIL', 'Readwoods <no-reply@readwoods.local>')

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
    ],
}

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/tree/'
LOGOUT_REDIRECT_URL = '/login/'
