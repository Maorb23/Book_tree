from django.contrib.auth.models import User
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
