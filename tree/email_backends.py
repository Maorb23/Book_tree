import requests

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import sanitize_address
from django.utils.encoding import force_str


class ResendEmailBackend(BaseEmailBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = settings.RESEND_API_KEY
        self.api_url = settings.RESEND_API_URL
        self.timeout = settings.RESEND_TIMEOUT

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            if self.fail_silently:
                return 0
            raise ValueError('RESEND_API_KEY is required when using ResendEmailBackend.')

        sent_count = 0
        for message in email_messages:
            try:
                self._send(message)
            except Exception:
                if not self.fail_silently:
                    raise
            else:
                sent_count += 1
        return sent_count

    def _send(self, message):
        payload = {
            'from': sanitize_address(message.from_email, 'utf-8'),
            'to': [
                sanitize_address(recipient, 'utf-8')
                for recipient in message.to
            ],
            'subject': force_str(message.subject),
        }

        if message.cc:
            payload['cc'] = [
                sanitize_address(recipient, 'utf-8')
                for recipient in message.cc
            ]
        if message.bcc:
            payload['bcc'] = [
                sanitize_address(recipient, 'utf-8')
                for recipient in message.bcc
            ]
        if message.reply_to:
            payload['reply_to'] = [
                sanitize_address(recipient, 'utf-8')
                for recipient in message.reply_to
            ]

        html = self._html_body(message)
        if html:
            payload['html'] = html
            if message.body:
                payload['text'] = force_str(message.body)
        else:
            payload['text'] = force_str(message.body)

        response = requests.post(
            self.api_url,
            headers={
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
                'User-Agent': 'Readwoods/1.0',
            },
            json=payload,
            timeout=self.timeout,
        )
        if not response.ok:
            raise requests.HTTPError(
                f'{response.status_code} error from Resend: {response.text}',
                response=response,
            )

    def _html_body(self, message):
        if getattr(message, 'content_subtype', '') == 'html':
            return force_str(message.body)

        for content, mimetype in getattr(message, 'alternatives', []):
            if mimetype == 'text/html':
                return force_str(content)
        return ''
