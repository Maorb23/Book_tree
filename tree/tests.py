from django.contrib.auth.models import User
from django.core import mail
from django.core.mail import EmailMessage
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from requests import HTTPError
from unittest.mock import patch

from .email_backends import ResendEmailBackend
from .models import FriendRequest, Friendship, CommunityPost
from book_tree.settings import _email_env


class CommunityModelTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='reader_a', password='pass1234')
        self.user_b = User.objects.create_user(username='reader_b', password='pass1234')

    def test_cannot_friend_self(self):
        with self.assertRaises(ValidationError):
            FriendRequest.objects.create(from_user=self.user_a, to_user=self.user_a)

    def test_cannot_create_duplicate_friend_requests(self):
        FriendRequest.objects.create(from_user=self.user_a, to_user=self.user_b)
        with self.assertRaises(ValidationError):
            FriendRequest.objects.create(from_user=self.user_a, to_user=self.user_b)

    def test_accepting_request_creates_connection(self):
        friend_request = FriendRequest.objects.create(from_user=self.user_a, to_user=self.user_b)
        self.client.force_login(self.user_b)
        response = self.client.post(reverse('tree:community-accept-request', args=[friend_request.id]))
        self.assertEqual(response.status_code, 302)

        friend_request.refresh_from_db()
        self.assertEqual(friend_request.status, FriendRequest.STATUS_ACCEPTED)
        self.assertTrue(
            Friendship.objects.filter(user_a=self.user_a, user_b=self.user_b).exists()
            or Friendship.objects.filter(user_a=self.user_b, user_b=self.user_a).exists()
        )

    def test_posts_attached_to_correct_user(self):
        post = CommunityPost.objects.create(
            user=self.user_a,
            title='New branch added',
            content='Added three sci-fi classics.',
        )
        self.assertEqual(post.user, self.user_a)


class RegistrationVerificationTests(TestCase):
    def test_registration_requires_email_verification(self):
        response = self.client.post(reverse('tree:register'), {
            'username': 'new_reader',
            'email': 'reader@example.com',
            'password1': 'A-strong-test-pass-123',
            'password2': 'A-strong-test-pass-123',
        })

        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username='new_reader')
        self.assertFalse(user.is_active)
        self.assertEqual(user.email, 'reader@example.com')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Verify your Readwoods account', mail.outbox[0].subject)

    def test_verification_link_activates_user(self):
        self.client.post(reverse('tree:register'), {
            'username': 'new_reader',
            'email': 'reader@example.com',
            'password1': 'A-strong-test-pass-123',
            'password2': 'A-strong-test-pass-123',
        })
        verification_url = [
            part for part in mail.outbox[0].body.split()
            if '/verify-email/' in part
        ][0]
        path = verification_url.split('testserver')[-1]

        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)

        user = User.objects.get(username='new_reader')
        self.assertTrue(user.is_active)
        self.assertEqual(str(self.client.session['_auth_user_id']), str(user.id))
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn('Welcome to Readwoods', mail.outbox[1].subject)

    @patch('tree.views.send_mail', side_effect=HTTPError('403 error from Resend'))
    def test_registration_email_api_failure_returns_form_error(self, mock_send_mail):
        response = self.client.post(reverse('tree:register'), {
            'username': 'new_reader',
            'email': 'reader@example.com',
            'password1': 'A-strong-test-pass-123',
            'password2': 'A-strong-test-pass-123',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'We could not send the verification email right now.')
        self.assertFalse(User.objects.filter(username='new_reader').exists())


class ResendEmailBackendTests(SimpleTestCase):
    @override_settings(
        RESEND_API_KEY='re_test_key',
        RESEND_API_URL='https://api.resend.com/emails',
        RESEND_TIMEOUT=10,
    )
    @patch('tree.email_backends.requests.post')
    def test_resend_backend_sends_email_via_https_api(self, mock_post):
        mock_post.return_value.raise_for_status.return_value = None
        message = EmailMessage(
            subject='Verify your Readwoods account',
            body='Open this link to verify.',
            from_email='Readwoods <verify@example.com>',
            to=['reader@example.com'],
        )

        sent_count = ResendEmailBackend().send_messages([message])

        self.assertEqual(sent_count, 1)
        mock_post.assert_called_once_with(
            'https://api.resend.com/emails',
            headers={
                'Authorization': 'Bearer re_test_key',
                'Content-Type': 'application/json',
                'User-Agent': 'Readwoods/1.0',
            },
            json={
                'from': 'Readwoods <verify@example.com>',
                'to': ['reader@example.com'],
                'subject': 'Verify your Readwoods account',
                'text': 'Open this link to verify.',
            },
            timeout=10,
        )


class EmailSettingsTests(SimpleTestCase):
    @override_settings()
    def test_email_env_normalizes_accidental_double_angle_brackets(self):
        with patch.dict('os.environ', {'DEFAULT_FROM_EMAIL': 'Readwoods <<verify@readwoods.com>>'}):
            self.assertEqual(
                _email_env('DEFAULT_FROM_EMAIL', ''),
                'Readwoods <verify@readwoods.com>',
            )
