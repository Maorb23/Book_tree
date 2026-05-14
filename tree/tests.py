from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import FriendRequest, Friendship, CommunityPost


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
