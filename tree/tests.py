from django.contrib.auth.models import User
from django.core.cache import cache
from django.core import mail
from django.core.mail import EmailMessage
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from requests import HTTPError
from unittest.mock import Mock, patch
from datetime import date, timedelta
import json

from .email_backends import ResendEmailBackend
from .models import (
    FriendRequest, Friendship, CommunityPost, Node, ImportedBook, BookReview,
    Tree, TreeVersion, ReadingChallenge, DailyPageLog,
)
from .views import (
    _apply_known_book_metadata, _book_rank, _cache_key, _get_library_books,
    _search_authors_open_library, _search_books_google, _search_books_open_library,
    _google_volume_to_row,
)
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
    def setUp(self):
        cache.clear()

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

    def test_known_metadata_preserves_dune_original_publication(self):
        row = _apply_known_book_metadata({
            'title': 'Dune',
            'author': 'Frank Herbert',
            'year': '2005',
            'isbn': '',
            'genre': '',
            'cover_url': '',
        })

        self.assertEqual(row['year'], '1965')
        self.assertEqual(row['isbn'], '9780441172719')

    def test_book_rank_prefers_title_author_match(self):
        dune = {'title': 'Dune', 'author': 'Frank Herbert', 'year': '1965', 'isbn': '9780441172719'}
        unrelated = {'title': 'Frank Herbert', 'author': 'William Touponce', 'year': '1988', 'isbn': '9780809313938'}

        self.assertGreater(_book_rank(dune, 'Dune Frank Herbert'), _book_rank(unrelated, 'Dune Frank Herbert'))

    def test_book_rank_prefers_known_literary_title_for_title_only_search(self):
        gass = {'title': 'The Tunnel', 'author': 'William H. Gass'}
        thriller = {
            'title': 'The Tunnel',
            'author': 'Popular Thriller Author',
            'year': '2018',
            'isbn': '9780000000000',
            'cover_url': 'https://example.com/tunnel.jpg',
        }

        self.assertGreater(_book_rank(gass, 'The Tunnel'), _book_rank(thriller, 'The Tunnel'))

    @patch('tree.views.requests.get')
    def test_open_library_search_uses_popularity_signals(self, mock_get):
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {
            'docs': [{
                'title': 'The Tunnel',
                'author_name': ['William H. Gass'],
                'first_publish_year': 1995,
                'isbn': ['9780000000000'],
                'edition_count': 24,
                'ratings_count': 12,
                'ratings_average': 4.1,
                'want_to_read_count': 40,
                'currently_reading_count': 3,
                'already_read_count': 80,
            }]
        }

        results = _search_books_open_library('The Tunnel')

        params = mock_get.call_args.kwargs['params']
        self.assertIn('edition_count', params['fields'])
        self.assertIn('ratings_count', params['fields'])
        self.assertEqual(results[0]['edition_count'], 24)
        self.assertEqual(results[0]['reader_count'], 123)

    @override_settings(GOOGLE_BOOKS_API_KEY='test-google-books-key')
    @patch('tree.views.requests.get')
    def test_google_books_search_sends_configured_api_key(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {'items': []}

        _search_books_google('Dune')

        self.assertEqual(mock_get.call_args.kwargs['params']['key'], 'test-google-books-key')

    def test_google_volume_to_row_includes_rating_metadata(self):
        row = _google_volume_to_row({
            'volumeInfo': {
                'title': 'Dune',
                'authors': ['Frank Herbert'],
                'averageRating': 4.5,
                'ratingsCount': 123,
            }
        })

        self.assertEqual(row['average_rating'], 4.5)
        self.assertEqual(row['ratings_count'], 123)

    @override_settings(GUARDIAN_API_KEY='guardian-test-key')
    @patch('tree.views.requests.get')
    def test_critic_reviews_uses_guardian_api_key(self, mock_get):
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {
            'response': {
                'results': [{
                    'webTitle': 'A Desert Epic',
                    'webPublicationDate': '1965-01-01T00:00:00Z',
                    'webUrl': 'https://www.theguardian.com/books/dune',
                    'fields': {
                        'headline': 'A Desert Epic',
                        'byline': 'A Critic',
                        'trailText': '<p>A review summary.</p>',
                    },
                }]
            }
        }

        response = self.client.get(reverse('tree:api-critic-reviews'), {'title': 'Dune', 'author': 'Frank Herbert'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['source'], 'The Guardian')
        self.assertEqual(response.json()['results'][0]['review_title'], 'A Desert Epic')
        self.assertEqual(response.json()['results'][0]['summary'], 'A review summary.')
        self.assertEqual(mock_get.call_args.kwargs['params']['api-key'], 'guardian-test-key')
        self.assertEqual(mock_get.call_args.kwargs['params']['section'], 'books')
        self.assertEqual(mock_get.call_args.kwargs['params']['order-by'], 'relevance')
        self.assertEqual(mock_get.call_args.kwargs['params']['page-size'], 2)
        self.assertIn('"Dune"', mock_get.call_args.kwargs['params']['q'])
        self.assertIn('"Frank Herbert"', mock_get.call_args.kwargs['params']['q'])
        self.assertEqual(mock_get.call_args.args[0], 'https://content.guardianapis.com/search')

    @override_settings(GUARDIAN_API_KEY='guardian-test-key')
    @patch('tree.views.requests.get')
    def test_critic_reviews_broadens_guardian_search_when_exact_query_has_no_results(self, mock_get):
        empty_response = Mock(status_code=200)
        empty_response.raise_for_status.return_value = None
        empty_response.json.return_value = {'response': {'results': []}}
        match_response = Mock(status_code=200)
        match_response.raise_for_status.return_value = None
        match_response.json.return_value = {
            'response': {
                'results': [{
                    'webTitle': 'A Desert Epic',
                    'webUrl': 'https://www.theguardian.com/books/dune',
                }]
            }
        }
        mock_get.side_effect = [empty_response, match_response]

        response = self.client.get(reverse('tree:api-critic-reviews'), {
            'title': 'Dune',
            'author': 'Frank Herbert',
            'isbn': '9780441172719',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['book_title'], 'Dune')
        self.assertNotIn('9780441172719', mock_get.call_args_list[0].kwargs['params']['q'])
        self.assertEqual(mock_get.call_args_list[0].kwargs['params']['q'], '"Dune" "Frank Herbert"')
        self.assertEqual(mock_get.call_args_list[1].kwargs['params']['q'], '"Dune"')

    @override_settings(GUARDIAN_API_KEY='')
    def test_critic_reviews_returns_disclaimer_without_key(self):
        response = self.client.get(reverse('tree:api-critic-reviews'), {'title': 'Dune'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [])
        self.assertIn('configured', response.json()['detail'])

    @patch('tree.views.requests.get')
    def test_author_search_returns_author_node_payloads(self, mock_get):
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {
            'docs': [
                {
                    'name': 'Ernest Hemingway',
                    'key': 'OL13640A',
                    'birth_date': 'July 21, 1899',
                    'top_work': 'The Old Man and the Sea',
                    'work_count': 400,
                }
            ]
        }

        results = _search_authors_open_library('Ernest Hemingway')

        self.assertEqual(results[0]['title'], 'Ernest Hemingway')
        self.assertEqual(results[0]['node_type'], 'author')
        self.assertEqual(results[0]['year'], '1899')
        self.assertEqual(results[0]['cover_url'], 'https://covers.openlibrary.org/a/olid/OL13640A-M.jpg')


class GoodreadsImportTests(TestCase):
    def setUp(self):
        cache.clear()
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

    def test_save_tree_creates_restorable_version(self):
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
        self.assertEqual(TreeVersion.objects.filter(user=self.user).count(), 0)

        response = self.client.post(
            reverse('tree:api-tree-version-create'),
            data=json.dumps({'label': 'Before title edit'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(TreeVersion.objects.filter(user=self.user).count(), 1)

        response = self.client.patch(
            reverse('tree:api-node-detail', args=[node_id]),
            data=json.dumps({'title': 'Dune Messiah'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TreeVersion.objects.filter(user=self.user).count(), 1)

        first_version = TreeVersion.objects.filter(user=self.user).order_by('created_at').first()
        response = self.client.post(reverse('tree:api-tree-version-restore', args=[first_version.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Node.objects.filter(user=self.user, title='Dune Messiah').exists())

    def test_save_tree_version_can_store_comment(self):
        tree = Tree.objects.create(user=self.user, name='Main Tree', is_default=True)
        Node.objects.create(user=self.user, tree=tree, title='Dune', author='Frank Herbert', node_type='book')

        response = self.client.post(
            reverse('tree:api-tree-version-create'),
            data=json.dumps({
                'tree_id': tree.id,
                'label': 'After adding Dune',
                'comment': 'Added the first science fiction branch.',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        version = TreeVersion.objects.get(user=self.user, tree=tree)
        self.assertEqual(version.comment, 'Added the first science fiction branch.')
        self.assertEqual(response.json()['comment'], 'Added the first science fiction branch.')

    def test_save_tree_version_can_create_community_tree_update(self):
        tree = Tree.objects.create(user=self.user, name='Main Tree', is_default=True)

        response = self.client.post(
            reverse('tree:api-tree-version-create'),
            data=json.dumps({
                'tree_id': tree.id,
                'comment': 'Added a Hemingway branch.',
                'visibility': Tree.VISIBILITY_FRIENDS,
                'post_to_community': True,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        tree.refresh_from_db()
        self.assertEqual(tree.visibility, Tree.VISIBILITY_FRIENDS)
        post = CommunityPost.objects.get(user=self.user, tree=tree)
        self.assertEqual(post.content, 'Added a Hemingway branch.')
        self.assertEqual(post.visibility, CommunityPost.VISIBILITY_FRIENDS)

    def test_book_review_api_creates_review_for_tree_node(self):
        tree = Tree.objects.create(user=self.user, name='Main Tree', is_default=True)
        node = Node.objects.create(user=self.user, tree=tree, title='Dune', author='Frank Herbert', node_type='book')

        response = self.client.post(
            reverse('tree:api-book-reviews'),
            data=json.dumps({
                'node': str(node.id),
                'title': 'Dune',
                'author': 'Frank Herbert',
                'review': 'Still enormous and strange.',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(BookReview.objects.get(user=self.user, node=node).review, 'Still enormous and strange.')

    def test_book_community_reviews_returns_matching_reviews(self):
        other_user = User.objects.create_user(username='other_reader', password='pass1234')
        BookReview.objects.create(
            user=other_user,
            title='Dune',
            author='Frank Herbert',
            isbn='9780441172719',
            rating=5,
            review='Sand, politics, worms. Perfect.',
        )

        response = self.client.get(reverse('tree:api-book-community-reviews'), {
            'title': 'Dune',
            'author': 'Frank Herbert',
            'isbn': '9780441172719',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]['username'], 'other_reader')
        self.assertEqual(response.json()[0]['review'], 'Sand, politics, worms. Perfect.')

    def test_book_shelves_returns_user_shelves_for_matching_book(self):
        ImportedBook.objects.create(
            user=self.user,
            title='Dune',
            author='Frank Herbert',
            isbn='9780441172719',
            shelf=Node.SHELF_READ,
            custom_shelf='desert books',
        )

        response = self.client.get(reverse('tree:api-book-shelves'), {
            'title': 'Dune',
            'author': 'Frank Herbert',
            'isbn': '9780441172719',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['shelves'][0]['label'], 'desert books')

    def test_book_page_uses_imported_book_metadata_first(self):
        imported_book = ImportedBook.objects.create(
            user=self.user,
            title='A Farewell to Arms',
            author='Ernest Hemingway',
            year=1929,
            isbn='9780099910107',
            cover_image='https://example.com/farewell.jpg',
            shelf=Node.SHELF_READ,
            custom_shelf='Americana',
        )

        response = self.client.get(reverse('tree:book'), {
            'imported_book': imported_book.id,
            'title': 'Wrong Title',
            'year': '1994',
            'cover': 'https://example.com/wrong.jpg',
        })

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('data-imported-book="%s"' % imported_book.id, content)
        self.assertIn('data-title="A Farewell to Arms"', content)
        self.assertIn('data-year="1929"', content)
        self.assertIn('data-cover-url="https://example.com/farewell.jpg"', content)

    def test_my_books_links_to_exact_imported_book_page(self):
        imported_book = ImportedBook.objects.create(
            user=self.user,
            title='A Farewell to Arms',
            author='Ernest Hemingway',
            year=1929,
            isbn='9780099910107',
            cover_image='https://example.com/farewell.jpg',
            shelf=Node.SHELF_READ,
        )

        response = self.client.get(reverse('tree:my-books'))

        self.assertEqual(response.status_code, 200)
        self.assertIn(f'imported_book={imported_book.id}', response.content.decode())

    def test_friends_can_view_friend_visible_shared_tree(self):
        friend = User.objects.create_user(username='friend', password='pass1234')
        Friendship.objects.create(user_a=self.user, user_b=friend)
        tree = Tree.objects.create(user=self.user, name='Friend Tree', visibility=Tree.VISIBILITY_FRIENDS)
        Node.objects.create(user=self.user, tree=tree, title='Dune', node_type='book')
        self.client.force_login(friend)

        response = self.client.get(reverse('tree:api-shared-tree', args=[self.user.username, tree.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['tree']['id'], tree.id)

    def test_non_friends_cannot_view_friend_visible_shared_tree(self):
        stranger = User.objects.create_user(username='stranger', password='pass1234')
        tree = Tree.objects.create(user=self.user, name='Friend Tree', visibility=Tree.VISIBILITY_FRIENDS)
        self.client.force_login(stranger)

        response = self.client.get(reverse('tree:api-shared-tree', args=[self.user.username, tree.id]))

        self.assertEqual(response.status_code, 403)

    def test_delete_tree_can_delete_default_and_promote_next_tree(self):
        main_tree = Tree.objects.create(user=self.user, name='Main Tree', is_default=True)
        next_tree = Tree.objects.create(user=self.user, name='Postmodern')
        Node.objects.create(user=self.user, tree=main_tree, title='Dune', node_type='book')

        response = self.client.delete(reverse('tree:api-tree-detail', args=[main_tree.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['next_tree_id'], next_tree.id)
        self.assertFalse(Tree.objects.filter(id=main_tree.id).exists())
        next_tree.refresh_from_db()
        self.assertTrue(next_tree.is_default)

    def test_delete_tree_allows_last_remaining_tree(self):
        tree = Tree.objects.create(user=self.user, name='Only Tree', is_default=True)

        response = self.client.delete(reverse('tree:api-tree-detail', args=[tree.id]))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['next_tree_id'])
        self.assertFalse(Tree.objects.filter(user=self.user).exists())

    def test_discard_tree_restores_submitted_snapshot_without_version(self):
        node = Node.objects.create(
            user=self.user,
            title='Dune',
            author='Frank Herbert',
            node_type='book',
            isbn='9780441172719',
        )
        snapshot = {
            'nodes': [{
                'id': str(node.id),
                'title': 'Dune',
                'node_type': 'book',
                'author': 'Frank Herbert',
                'isbn': '9780441172719',
                'parent': None,
            }],
            'edges': [{
                'id': f'parent-{node.id}',
                'source': str(node.id),
                'target': str(node.id),
                'edge_type': 'progression',
            }],
        }
        node.title = 'Dune Messiah'
        node.save(update_fields=['title'])

        response = self.client.post(
            reverse('tree:api-tree-discard'),
            data=json.dumps({'snapshot': snapshot}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Node.objects.filter(user=self.user, title='Dune').exists())
        self.assertFalse(Node.objects.filter(user=self.user, title='Dune Messiah').exists())
        self.assertEqual(TreeVersion.objects.filter(user=self.user).count(), 0)

    def test_imported_book_can_be_added_under_tree_parent(self):
        parent = Node.objects.create(
            user=self.user,
            title='Science Fiction',
            node_type='genre',
        )
        imported_book = ImportedBook.objects.create(
            user=self.user,
            title='Dune',
            author='Frank Herbert',
            isbn='9780441172719',
            shelf=Node.SHELF_WANT_TO_READ,
        )

        response = self.client.post(
            reverse('tree:api-imported-book-add-to-tree', args=[imported_book.id]),
            data=json.dumps({'parent': str(parent.id)}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        node = Node.objects.get(user=self.user, title='Dune')
        self.assertEqual(node.parent, parent)

    def test_imported_book_can_be_added_under_author_parent(self):
        parent = Node.objects.create(
            user=self.user,
            title='Frank Herbert',
            node_type='author',
        )
        imported_book = ImportedBook.objects.create(
            user=self.user,
            title='Dune',
            author='Frank Herbert',
            isbn='9780441172719',
            shelf=Node.SHELF_WANT_TO_READ,
        )

        response = self.client.post(
            reverse('tree:api-imported-book-add-to-tree', args=[imported_book.id]),
            data=json.dumps({'parent': str(parent.id)}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        node = Node.objects.get(user=self.user, title='Dune')
        self.assertEqual(node.parent, parent)

    def test_auto_tree_from_shelf_rejects_more_than_fifteen_books(self):
        for index in range(16):
            ImportedBook.objects.create(
                user=self.user,
                title=f'Book {index}',
                author='Shared Author',
                custom_shelf='postmodern',
            )

        response = self.client.post(
            reverse('tree:api-tree-auto-from-shelf'),
            data=json.dumps({
                'shelf': 'postmodern',
                'shelf_type': 'custom',
                'mode': 'author',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['max_books'], 15)

    @patch('tree.views._search_authors_open_library')
    @patch('tree.views._search_books_combined', return_value=[])
    def test_auto_tree_from_shelf_groups_books_under_authors(self, mock_book_search, mock_author_search):
        mock_author_search.return_value = [{
            'title': 'Thomas Pynchon',
            'node_type': 'author',
            'year': '1937',
            'cover_url': 'https://example.com/pynchon.jpg',
            'description': 'Gravitys Rainbow',
        }]
        ImportedBook.objects.create(
            user=self.user,
            title='The Crying of Lot 49',
            author='Thomas Pynchon',
            custom_shelf='postmodern',
            isbn='9780060913076',
        )

        response = self.client.post(
            reverse('tree:api-tree-auto-from-shelf'),
            data=json.dumps({
                'shelf': 'postmodern',
                'shelf_type': 'custom',
                'mode': 'author',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        author = Node.objects.get(user=self.user, node_type='author', title='Thomas Pynchon')
        book = Node.objects.get(user=self.user, node_type='book', title='The Crying of Lot 49')
        self.assertEqual(book.parent, author)
        self.assertEqual(author.year, 1937)
        self.assertEqual(author.cover_image, 'https://example.com/pynchon.jpg')
        self.assertEqual(TreeVersion.objects.filter(user=self.user, reason='auto_tree').count(), 1)

    @patch('tree.views._search_authors_open_library')
    @patch('tree.views._search_books_combined', return_value=[])
    def test_auto_tree_retries_empty_author_cache_for_author_images(self, mock_book_search, mock_author_search):
        cache.set(_cache_key('auto-tree:author:v1', 'don delillo'), [], timeout=60 * 60 * 24)
        mock_author_search.return_value = [{
            'title': 'Don DeLillo',
            'node_type': 'author',
            'year': '1936',
            'cover_url': 'https://covers.openlibrary.org/a/olid/OL28267A-M.jpg',
            'description': 'White Noise',
        }]
        ImportedBook.objects.create(
            user=self.user,
            title='White Noise',
            author='Don DeLillo',
            custom_shelf='postmodern',
            isbn='9780143105985',
        )

        response = self.client.post(
            reverse('tree:api-tree-auto-from-shelf'),
            data=json.dumps({
                'shelf': 'postmodern',
                'shelf_type': 'custom',
                'mode': 'author',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        author = Node.objects.get(user=self.user, node_type='author', title='Don DeLillo')
        self.assertEqual(author.cover_image, 'https://covers.openlibrary.org/a/olid/OL28267A-L.jpg')
        mock_author_search.assert_called_once()

    @patch('tree.views._search_authors_open_library', return_value=[])
    @patch('tree.views._search_books_combined', return_value=[])
    def test_auto_tree_from_shelf_can_create_a_separate_tree(self, mock_book_search, mock_author_search):
        main_tree = Tree.objects.create(user=self.user, name='Main Tree', is_default=True)
        Node.objects.create(user=self.user, tree=main_tree, title='Existing Root', node_type='custom')
        ImportedBook.objects.create(
            user=self.user,
            title='White Noise',
            author='Don DeLillo',
            custom_shelf='postmodern',
            isbn='9780143105985',
        )

        response = self.client.post(
            reverse('tree:api-tree-auto-from-shelf'),
            data=json.dumps({
                'shelf': 'postmodern',
                'shelf_type': 'custom',
                'mode': 'author',
                'destination': 'new',
                'tree_name': 'Postmodern Authors',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        new_tree = Tree.objects.get(user=self.user, name='Postmodern Authors')
        self.assertNotEqual(new_tree.id, main_tree.id)
        self.assertEqual(Node.objects.filter(user=self.user, tree=main_tree).count(), 1)
        self.assertTrue(Node.objects.filter(user=self.user, tree=new_tree, title='Don DeLillo').exists())
        self.assertTrue(Node.objects.filter(user=self.user, tree=new_tree, title='White Noise').exists())

    @patch('tree.views._search_authors_open_library', return_value=[])
    @patch('tree.views._search_books_combined', return_value=[])
    def test_auto_tree_created_books_do_not_duplicate_my_books_library(self, mock_book_search, mock_author_search):
        ImportedBook.objects.create(
            user=self.user,
            title='White Noise',
            author='Don DeLillo',
            custom_shelf='postmodern',
            isbn='9780143105985',
        )

        response = self.client.post(
            reverse('tree:api-tree-auto-from-shelf'),
            data=json.dumps({
                'shelf': 'postmodern',
                'shelf_type': 'custom',
                'mode': 'author',
                'destination': 'new',
                'tree_name': 'Postmodern Authors',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        source = ImportedBook.objects.get(user=self.user, title='White Noise')
        self.assertEqual(source.custom_shelf, 'postmodern')
        generated = Node.objects.get(user=self.user, node_type='book', title='White Noise')
        self.assertTrue(generated.style.get('library_shadow'))
        library_books = _get_library_books(self.user)
        self.assertEqual(len(library_books), 1)
        self.assertEqual(library_books[0].library_source, 'imported')

    def test_my_books_library_dedupes_imported_and_tree_books_for_user(self):
        Tree.objects.create(user=self.user, name='Main Tree', is_default=True)
        ImportedBook.objects.create(
            user=self.user,
            title='Dune',
            author='Frank Herbert',
            isbn='9780441172719',
            shelf=Node.SHELF_READ,
        )
        Node.objects.create(
            user=self.user,
            title='Dune',
            author='Frank Herbert',
            isbn='9780441172719',
            node_type='book',
            shelf=Node.SHELF_WANT_TO_READ,
        )

        library_books = _get_library_books(self.user)

        self.assertEqual(len(library_books), 1)
        self.assertEqual(library_books[0].library_source, 'imported')
        self.assertEqual(library_books[0].shelf, Node.SHELF_READ)

    @patch('tree.views._search_authors_open_library', return_value=[])
    @patch('tree.views._search_books_combined', return_value=[])
    def test_auto_tree_from_shelf_is_idempotent(self, mock_book_search, mock_author_search):
        tree = Tree.objects.create(user=self.user, name='Postmodern Authors', is_default=True)
        ImportedBook.objects.create(
            user=self.user,
            title='White Noise',
            author='Don DeLillo',
            custom_shelf='postmodern',
            isbn='9780143105985',
        )

        payload = json.dumps({
            'shelf': 'postmodern',
            'shelf_type': 'custom',
            'mode': 'author',
            'destination': 'existing',
            'tree_id': tree.id,
        })
        first = self.client.post(
            reverse('tree:api-tree-auto-from-shelf'),
            data=payload,
            content_type='application/json',
        )
        second = self.client.post(
            reverse('tree:api-tree-auto-from-shelf'),
            data=payload,
            content_type='application/json',
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(Node.objects.filter(user=self.user, tree=tree, node_type='author', title='Don DeLillo').count(), 1)
        self.assertEqual(Node.objects.filter(user=self.user, tree=tree, node_type='book', title='White Noise').count(), 1)
        self.assertEqual(second.json()['reused_books'], 1)

    @patch('tree.views._search_authors_open_library', side_effect=SystemExit(1))
    @patch('tree.views._search_books_combined', side_effect=SystemExit(1))
    def test_auto_tree_from_shelf_does_not_depend_on_live_external_lookup(self, mock_book_search, mock_author_search):
        ImportedBook.objects.create(
            user=self.user,
            title='White Noise',
            author='Don DeLillo',
            custom_shelf='postmodern',
            isbn='9780143105985',
        )

        response = self.client.post(
            reverse('tree:api-tree-auto-from-shelf'),
            data=json.dumps({
                'shelf': 'postmodern',
                'shelf_type': 'custom',
                'mode': 'author',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertFalse(mock_book_search.called)
        author = Node.objects.get(user=self.user, node_type='author', title='Don DeLillo')
        book = Node.objects.get(user=self.user, node_type='book', title='White Noise')
        self.assertEqual(book.parent, author)

    @patch('tree.views._search_books_combined', return_value=[])
    def test_recommendations_exclude_books_already_in_my_books(self, mock_book_search):
        Node.objects.create(
            user=self.user,
            title='Dune',
            author='Frank Herbert',
            genre='Fiction - Science Fiction',
            node_type='book',
            isbn='9780441172719',
            shelf=Node.SHELF_READ,
            rating=5,
        )

        response = self.client.get(reverse('tree:api-my-books-recommendations'))

        self.assertEqual(response.status_code, 200)
        titles = {book['title'] for book in response.json()['results']}
        self.assertNotIn('Dune', titles)
        self.assertIn('The Left Hand of Darkness', titles)

    def test_challenge_target_can_be_updated(self):
        response = self.client.post(
            reverse('tree:api-challenge-target'),
            data=json.dumps({'target_books': 42}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        challenge = ReadingChallenge.objects.get(user=self.user, year=2026)
        self.assertEqual(challenge.target_books, 42)
        self.assertEqual(response.json()['challenge']['target_books'], 42)

    def test_reading_update_counts_only_currently_reading_books(self):
        book = Node.objects.create(
            user=self.user,
            title='Dune',
            author='Frank Herbert',
            node_type='book',
            shelf=Node.SHELF_CURRENTLY_READING,
        )

        response = self.client.post(
            reverse('tree:api-reading-update'),
            data=json.dumps({
                'source': 'tree',
                'book_id': str(book.id),
                'pages': 55,
                'log_date': date.today().isoformat(),
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(DailyPageLog.objects.filter(user=self.user, node=book).count(), 1)
        self.assertEqual(response.json()['current_page_streak'], 1)

    @override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
    def test_page_streak_personal_best_tracks_consecutive_50_page_days(self):
        book = Node.objects.create(
            user=self.user,
            title='Dune',
            author='Frank Herbert',
            node_type='book',
            shelf=Node.SHELF_CURRENTLY_READING,
        )
        for offset in (2, 1, 0):
            DailyPageLog.objects.create(
                user=self.user,
                node=book,
                book_title=book.title,
                book_author=book.author,
                pages=50,
                log_date=date.today() - timedelta(days=offset),
            )

        response = self.client.get(reverse('tree:challenges'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Personal best: 3 days')
