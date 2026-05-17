from django.contrib.auth.models import User
from django.core import mail
from django.core.mail import EmailMessage
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from requests import HTTPError
from unittest.mock import patch
import json

from .email_backends import ResendEmailBackend
from .models import FriendRequest, Friendship, CommunityPost, Node, ImportedBook, TreeVersion
from .views import _apply_known_book_metadata
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

    def test_owner_can_edit_and_delete_own_post(self):
        post = CommunityPost.objects.create(
            user=self.user_a,
            title='Old title',
            content='Old content',
        )
        self.client.force_login(self.user_a)

        response = self.client.post(reverse('tree:community-edit-post', args=[post.id]), {
            'title': 'Updated title',
            'content': 'Updated content',
            'progress_status': CommunityPost.STATUS_READING,
            'visibility': CommunityPost.VISIBILITY_FRIENDS,
        })

        self.assertEqual(response.status_code, 302)
        post.refresh_from_db()
        self.assertEqual(post.title, 'Updated title')
        self.assertEqual(post.visibility, CommunityPost.VISIBILITY_FRIENDS)

        response = self.client.post(reverse('tree:community-delete-post', args=[post.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CommunityPost.objects.filter(id=post.id).exists())


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


class BookSearchMetadataTests(SimpleTestCase):
    def test_known_metadata_preserves_beloved_original_publication(self):
        row = _apply_known_book_metadata({
            'title': 'Beloved',
            'author': 'Toni Morrison',
            'year': '2007',
            'isbn': '',
            'genre': '',
            'cover_url': '',
        })

        self.assertEqual(row['year'], '1987')
        self.assertEqual(row['isbn'], '9781400033416')


class GoodreadsImportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='reader', password='pass1234')
        self.client.force_login(self.user)

    def test_preview_marks_books_that_already_exist_in_tree(self):
        Node.objects.create(
            user=self.user,
            title='Beloved',
            author='Toni Morrison',
            node_type='book',
            isbn='9781400033416',
        )
        csv_body = (
            'Book Id,Title,Author,ISBN,ISBN13,My Rating,Year Published,Original Publication Year,'
            'Date Read,Bookshelves,Exclusive Shelf,My Review\n'
            '1,Beloved,Toni Morrison,,9781400033416,5,2004,1987,2024/01/02,favorites,read,Excellent\n'
            '2,Dune,Frank Herbert,,9780441172719,4,1990,1965,,sci-fi,to-read,\n'
        )

        response = self.client.post(
            reverse('tree:api-goodreads-preview'),
            {'csv_file': SimpleUploadedFile('goodreads.csv', csv_body.encode('utf-8'), content_type='text/csv')},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['total'], 2)
        self.assertEqual(payload['existing_count'], 1)
        self.assertEqual(payload['importable_count'], 1)

    def test_confirm_import_skips_existing_tree_books(self):
        Node.objects.create(
            user=self.user,
            title='Beloved',
            author='Toni Morrison',
            node_type='book',
            isbn='9781400033416',
        )

        response = self.client.post(
            reverse('tree:api-goodreads-import'),
            data=json.dumps({
                'books': [
                    {
                        'title': 'Beloved',
                        'author': 'Toni Morrison',
                        'isbn': '9781400033416',
                        'shelf': Node.SHELF_READ,
                    },
                    {
                        'title': 'Dune',
                        'author': 'Frank Herbert',
                        'isbn': '9780441172719',
                        'year': 1965,
                        'shelf': Node.SHELF_WANT_TO_READ,
                    },
                ],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload['created_count'], 1)
        self.assertEqual(payload['skipped_count'], 1)
        self.assertTrue(ImportedBook.objects.filter(user=self.user, title='Dune').exists())
        self.assertFalse(Node.objects.filter(user=self.user, title='Dune').exists())
        self.assertEqual(Node.objects.filter(user=self.user, title='Beloved').count(), 1)

    def test_tree_mutations_create_restorable_versions(self):
        response = self.client.post(
            reverse('tree:api-node-list'),
            data=json.dumps({
                'title': 'Dune',
                'author': 'Frank Herbert',
                'node_type': 'book',
                'isbn': '9780441172719',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        node_id = response.json()['id']
        self.assertEqual(TreeVersion.objects.filter(user=self.user).count(), 1)

        response = self.client.patch(
            reverse('tree:api-node-detail', args=[node_id]),
            data=json.dumps({'title': 'Dune Messiah'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TreeVersion.objects.filter(user=self.user).count(), 2)

        first_version = TreeVersion.objects.filter(user=self.user).order_by('created_at').first()
        response = self.client.post(reverse('tree:api-tree-version-restore', args=[first_version.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Node.objects.filter(user=self.user, title='Dune Messiah').exists())
