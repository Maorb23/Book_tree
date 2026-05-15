import requests
import logging
from concurrent.futures import ThreadPoolExecutor
import random
import re
from smtplib import SMTPException
from requests import RequestException
from html import unescape
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.db.models import Q, Count
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.cache import cache
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.urls import reverse
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Node, Edge, FriendRequest, Friendship, CommunityPost
from .serializers import NodeSerializer, EdgeSerializer
from .forms import EmailUserCreationForm


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Page views
# ──────────────────────────────────────────────

def landing(request):
    return render(request, 'landing.html', {
        'recommended_books': _get_landing_recommendations(),
        'reading_content': _get_reading_content(),
    })


def book_page(request):
    return render(request, 'book.html', {
        'title': (request.GET.get('title') or '').strip(),
        'author': (request.GET.get('author') or '').strip(),
        'isbn': (request.GET.get('isbn') or '').strip(),
        'genre': (request.GET.get('genre') or '').strip(),
        'year': (request.GET.get('year') or '').strip(),
        'cover_url': (request.GET.get('cover') or '').strip(),
        'description': (request.GET.get('description') or '').strip(),
    })


@login_required
def tree_page(request):
    return render(request, 'tree.html')


@login_required
def my_books(request):
    books = Node.objects.filter(user=request.user, node_type='book').order_by('title')
    shelf_counts = {
        'all': books.count(),
        Node.SHELF_WANT_TO_READ: books.filter(shelf=Node.SHELF_WANT_TO_READ).count(),
        Node.SHELF_CURRENTLY_READING: books.filter(shelf=Node.SHELF_CURRENTLY_READING).count(),
        Node.SHELF_READ: books.filter(shelf=Node.SHELF_READ).count(),
        Node.SHELF_DID_NOT_FINISH: books.filter(shelf=Node.SHELF_DID_NOT_FINISH).count(),
    }
    custom_shelves = (
        books.exclude(custom_shelf='')
        .values('custom_shelf')
        .annotate(total=Count('id'))
        .order_by('custom_shelf')
    )
    return render(request, 'my_books.html', {
        'books': books,
        'shelf_choices': Node.SHELF_CHOICES,
        'shelf_counts': shelf_counts,
        'custom_shelves': custom_shelves,
    })


def register_view(request):
    if request.user.is_authenticated:
        return redirect('tree:tree')

    form = EmailUserCreationForm(request.POST or None)
    next_url = request.POST.get('next') or request.GET.get('next')
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        try:
            _send_verification_email(request, user)
        except (SMTPException, RequestException, OSError, TimeoutError, ValueError):
            logger.exception('Verification email failed for user_id=%s email=%s', user.id, user.email)
            user.delete()
            form.add_error(
                None,
                'We could not send the verification email right now. Please check the site email settings or try again later.',
            )
            return render(request, 'register.html', {
                'form': form,
                'next_url': next_url,
            })
        return render(request, 'register.html', {
            'form': None,
            'next_url': next_url,
            'verification_sent': True,
            'email': user.email,
        })

    return render(request, 'register.html', {
        'form': form,
        'next_url': next_url,
    })


def verify_email_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save(update_fields=['is_active'])
        try:
            _send_welcome_email(user)
        except (SMTPException, RequestException, OSError, TimeoutError, ValueError):
            logger.exception('Welcome email failed for user_id=%s email=%s', user.id, user.email)
        login(request, user)
        return render(request, 'login.html', {
            'form': None,
            'verified': True,
        })

    return render(request, 'login.html', {
        'form': AuthenticationForm(request),
        'verification_error': True,
    })


def _send_verification_email(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    verify_url = request.build_absolute_uri(
        reverse('tree:verify-email', args=[uid, token])
    )
    subject = 'Verify your Readwoods account'
    message = (
        f'Hi {user.username},\n\n'
        'Welcome to Readwoods. Please verify your email address to activate your account:\n\n'
        f'{verify_url}\n\n'
        'If you did not create this account, you can ignore this email.'
    )
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


def _send_welcome_email(user):
    subject = 'Welcome to Readwoods'
    message = (
        f'Hi {user.username},\n\n'
        'Your email is verified and your Readwoods account is active.\n\n'
        'You can now save your reading tree, track books, and share progress with friends.\n\n'
        'Happy reading,\n'
        'The Readwoods team'
    )
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


def login_view(request):
    if request.user.is_authenticated:
        return redirect('tree:tree')

    next_url = request.POST.get('next') or request.GET.get('next')
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        return redirect(next_url or 'tree:tree')

    return render(request, 'login.html', {
        'form': form,
        'next_url': next_url,
        'logged_out': request.GET.get('logged_out') == '1',
    })


def logout_view(request):
    if request.user.is_authenticated:
        logout(request)
    return redirect('/login/?logged_out=1')


def _get_friend_ids(user):
    pairs = Friendship.objects.filter(Q(user_a=user) | Q(user_b=user)).values_list('user_a_id', 'user_b_id')
    friend_ids = set()
    for user_a_id, user_b_id in pairs:
        friend_ids.add(user_b_id if user_a_id == user.id else user_a_id)
    return friend_ids


def _get_display_name(user):
    profile = getattr(user, 'profile', None)
    if profile and profile.display_name:
        return profile.display_name
    return user.username


# ──────────────────────────────────────────────
# Community pages
# ──────────────────────────────────────────────

@login_required
def community_feed(request):
    friend_ids = _get_friend_ids(request.user)
    posts = CommunityPost.objects.select_related('user').filter(
        Q(visibility=CommunityPost.VISIBILITY_PUBLIC)
        | Q(user=request.user)
        | Q(visibility=CommunityPost.VISIBILITY_FRIENDS, user_id__in=friend_ids)
    )

    return render(request, 'community_feed.html', {
        'posts': posts,
    })


@login_required
def community_my_posts(request):
    posts = CommunityPost.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'community_my_posts.html', {
        'posts': posts,
    })


@login_required
def community_create_post(request):
    errors = []
    payload = {
        'title': '',
        'content': '',
        'progress_status': '',
        'visibility': CommunityPost.VISIBILITY_PUBLIC,
    }

    if request.method == 'POST':
        payload['title'] = (request.POST.get('title') or '').strip()
        payload['content'] = (request.POST.get('content') or '').strip()
        payload['progress_status'] = (request.POST.get('progress_status') or '').strip()
        payload['visibility'] = (request.POST.get('visibility') or CommunityPost.VISIBILITY_PUBLIC).strip()

        if not payload['title']:
            errors.append('Please add a title for your update.')
        if not payload['content']:
            errors.append('Please add some content for your update.')

        if not errors:
            CommunityPost.objects.create(
                user=request.user,
                title=payload['title'],
                content=payload['content'],
                progress_status=payload['progress_status'],
                visibility=payload['visibility'],
            )
            return redirect('tree:community-feed')

    return render(request, 'community_create_post.html', {
        'errors': errors,
        'form': payload,
        'status_choices': CommunityPost.STATUS_CHOICES,
        'visibility_choices': CommunityPost.VISIBILITY_CHOICES,
    })


@login_required
def community_people(request):
    query = (request.GET.get('q') or '').strip()
    users = User.objects.exclude(id=request.user.id)
    if query:
        users = users.filter(username__icontains=query)
    users = users.order_by('username')

    friend_ids = _get_friend_ids(request.user)
    outgoing_ids = set(
        FriendRequest.objects.filter(
            from_user=request.user,
            status=FriendRequest.STATUS_PENDING,
        ).values_list('to_user_id', flat=True)
    )
    incoming_ids = set(
        FriendRequest.objects.filter(
            to_user=request.user,
            status=FriendRequest.STATUS_PENDING,
        ).values_list('from_user_id', flat=True)
    )

    people = []
    for user in users:
        if user.id in friend_ids:
            status_label = 'friend'
        elif user.id in outgoing_ids:
            status_label = 'outgoing'
        elif user.id in incoming_ids:
            status_label = 'incoming'
        else:
            status_label = 'none'

        people.append({
            'user': user,
            'display_name': _get_display_name(user),
            'status': status_label,
        })

    return render(request, 'community_people.html', {
        'people': people,
        'query': query,
    })


@login_required
def community_requests(request):
    incoming = FriendRequest.objects.filter(
        to_user=request.user,
        status=FriendRequest.STATUS_PENDING,
    ).select_related('from_user')
    outgoing = FriendRequest.objects.filter(
        from_user=request.user,
        status=FriendRequest.STATUS_PENDING,
    ).select_related('to_user')

    return render(request, 'community_requests.html', {
        'incoming': incoming,
        'outgoing': outgoing,
    })


@login_required
def community_friends(request):
    friend_ids = _get_friend_ids(request.user)
    friends = User.objects.filter(id__in=friend_ids).order_by('username')
    friend_cards = [
        {
            'user': friend,
            'display_name': _get_display_name(friend),
        }
        for friend in friends
    ]
    return render(request, 'community_friends.html', {
        'friends': friend_cards,
    })


@login_required
@require_http_methods(['POST'])
def send_friend_request(request, user_id):
    to_user = get_object_or_404(User, pk=user_id)
    if to_user.id == request.user.id:
        return redirect('tree:community-people')

    friend_exists = Friendship.objects.filter(
        Q(user_a=request.user, user_b=to_user) | Q(user_a=to_user, user_b=request.user)
    ).exists()
    if friend_exists:
        return redirect('tree:community-people')

    try:
        FriendRequest.objects.create(from_user=request.user, to_user=to_user)
    except IntegrityError:
        pass

    return redirect('tree:community-people')


@login_required
@require_http_methods(['POST'])
def accept_friend_request(request, request_id):
    friend_request = get_object_or_404(
        FriendRequest,
        id=request_id,
        to_user=request.user,
        status=FriendRequest.STATUS_PENDING,
    )

    friend_request.status = FriendRequest.STATUS_ACCEPTED
    friend_request.save(update_fields=['status', 'updated_at'])

    try:
        Friendship.objects.create(user_a=friend_request.from_user, user_b=friend_request.to_user)
    except IntegrityError:
        pass

    return redirect('tree:community-requests')


@login_required
@require_http_methods(['POST'])
def reject_friend_request(request, request_id):
    friend_request = get_object_or_404(
        FriendRequest,
        id=request_id,
        to_user=request.user,
        status=FriendRequest.STATUS_PENDING,
    )

    friend_request.status = FriendRequest.STATUS_REJECTED
    friend_request.save(update_fields=['status', 'updated_at'])

    return redirect('tree:community-requests')


# ──────────────────────────────────────────────
# Tree data – full snapshot
# ──────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tree_data(request):
    """Return all nodes + edges for the frontend to render."""
    cache_key = f'tree-data:v1:user:{request.user.id}'
    cached = cache.get(cache_key)
    if cached:
        return Response(cached)

    nodes = Node.objects.filter(user=request.user).annotate(children_count=Count('children'))
    edges = Edge.objects.select_related('source', 'target').filter(user=request.user)

    node_data = NodeSerializer(nodes, many=True, context={'request': request}).data

    # Build parent-based edges (tree structure) plus explicit edges
    edge_data = []
    for node in nodes:
        if node.parent_id:
            edge_data.append({
                'id': f"parent-{node.id}",
                'source': str(node.parent_id),
                'target': str(node.id),
                'edge_type': 'progression',
                'label': '',
                'style': {},
            })

    for edge in edges:
        edge_data.append(EdgeSerializer(edge).data)

    payload = {'nodes': node_data, 'edges': edge_data}
    cache.set(cache_key, payload, timeout=60)
    return Response(payload)


# ──────────────────────────────────────────────
# Node CRUD
# ──────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def node_list(request):
    if request.method == 'GET':
        nodes = Node.objects.filter(user=request.user).annotate(children_count=Count('children'))
        serializer = NodeSerializer(nodes, many=True, context={'request': request})
        return Response(serializer.data)

    serializer = NodeSerializer(data=request.data)
    if serializer.is_valid():
        node = serializer.save(user=request.user)
        # Auto-fetch cover if not supplied
        if not node.cover_image and node.isbn:
            node.cover_image = _fetch_cover_open_library(node.isbn)
            node.save(update_fields=['cover_image'])
        elif not node.cover_image and node.title:
            node.cover_image = _fetch_cover_google(node.title, node.author)
            node.save(update_fields=['cover_image'])
        _invalidate_tree_cache(request.user.id)
        return Response(
            NodeSerializer(node, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def node_detail(request, pk):
    node = get_object_or_404(
        Node.objects.annotate(children_count=Count('children')).filter(user=request.user),
        pk=pk,
    )

    if request.method == 'GET':
        return Response(NodeSerializer(node, context={'request': request}).data)

    if request.method in ('PUT', 'PATCH'):
        serializer = NodeSerializer(node, data=request.data,
                                    partial=(request.method == 'PATCH'),
                                    context={'request': request})
        if serializer.is_valid():
            serializer.save()
            _invalidate_tree_cache(request.user.id)
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    node.delete()
    _invalidate_tree_cache(request.user.id)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def edge_list(request):
    if request.method == 'GET':
        edges = Edge.objects.filter(user=request.user)
        serializer = EdgeSerializer(edges, many=True)
        return Response(serializer.data)

    serializer = EdgeSerializer(data=request.data)
    if serializer.is_valid():
        source = serializer.validated_data['source']
        target = serializer.validated_data['target']
        edge_type = serializer.validated_data.get('edge_type', 'custom')

        if source.user_id != request.user.id or target.user_id != request.user.id:
            return Response(
                {'detail': 'Source and target must belong to the current user.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if source.id == target.id:
            return Response(
                {'detail': 'Source and target must be different nodes.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if Edge.objects.filter(
            user=request.user,
            source=source,
            target=target,
            edge_type=edge_type,
        ).exists():
            return Response(
                {'detail': 'This connection already exists.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        edge = serializer.save(user=request.user)
        _invalidate_tree_cache(request.user.id)
        return Response(EdgeSerializer(edge).data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def edge_detail(request, pk):
    edge = get_object_or_404(Edge.objects.filter(user=request.user), pk=pk)

    if request.method == 'PATCH':
        serializer = EdgeSerializer(edge, data=request.data, partial=True)
        if serializer.is_valid():
            saved = serializer.save()
            _invalidate_tree_cache(request.user.id)
            return Response(EdgeSerializer(saved).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    edge.delete()
    _invalidate_tree_cache(request.user.id)
    return Response(status=status.HTTP_204_NO_CONTENT)


def _invalidate_tree_cache(user_id):
    cache.delete(f'tree-data:v1:user:{user_id}')


# ──────────────────────────────────────────────
# Cover image lookup
# ──────────────────────────────────────────────

@api_view(['GET'])
def fetch_cover(request):
    title = request.query_params.get('title', '')
    author = request.query_params.get('author', '')
    isbn = request.query_params.get('isbn', '')

    url = None
    if isbn:
        url = _fetch_cover_open_library(isbn)
    if not url and title:
        url = _fetch_cover_google(title, author)

    return Response({'cover_url': url or ''})


@api_view(['GET'])
def search_books(request):
    """Autocomplete books by title and return metadata, including ISBN."""
    query = (request.query_params.get('q') or '').strip()
    if len(query) < 2:
        return Response({'results': []})

    cache_key = f"book-search:v3:{query.lower()}"
    cached_results = cache.get(cache_key)
    if cached_results is not None:
        return Response({'results': cached_results})

    results = _search_books_combined(query)
    cache.set(cache_key, results, timeout=60 * 30)
    return Response({'results': results})


def _search_books_combined(query):
    with ThreadPoolExecutor(max_workers=2) as executor:
        google_future = executor.submit(_search_books_google, query)
        open_library_future = executor.submit(_search_books_open_library, query)

        try:
            google_results = google_future.result(timeout=4.5)
        except Exception:
            logger.exception('Google Books lookup failed for query=%r', query)
            google_results = []

        try:
            open_library_results = open_library_future.result(timeout=4.5)
        except Exception:
            logger.exception('Open Library lookup failed for query=%r', query)
            open_library_results = []

    google_by_title = {}
    for row in google_results:
        google_by_title.setdefault(_normalize_text(row.get('title')), row)

    merged = []
    seen = set()
    ordered_rows = sorted(
        open_library_results,
        key=lambda row: _book_rank(row, query),
        reverse=True,
    ) + sorted(
        google_results,
        key=lambda row: _book_rank(row, query),
        reverse=True,
    )

    for row in ordered_rows:
        key = _book_key(row.get('title'), row.get('author'))
        if not key or key in seen:
            continue
        seen.add(key)
        google_match = google_by_title.get(_normalize_text(row.get('title')), {})
        canonical = row if row in open_library_results else {}
        merged_row = {
            **row,
            'genre': _genre_label(canonical.get('genre') or row.get('genre') or ''),
            'year': canonical.get('year') or row.get('year') or '',
            'isbn': _best_isbn(
                canonical.get('isbn_options')
                or row.get('isbn_options')
                or google_match.get('isbn_options')
                or [row.get('isbn'), google_match.get('isbn')]
            ),
            'description': row.get('description') or google_match.get('description') or '',
        }
        if canonical.get('cover_url') and not merged_row.get('cover_url'):
            merged_row['cover_url'] = canonical['cover_url']
        if google_match.get('cover_url') and not merged_row.get('cover_url'):
            merged_row['cover_url'] = google_match['cover_url']
        merged_row = _apply_known_book_metadata(merged_row)
        merged_row.pop('isbn_options', None)
        merged.append(merged_row)

    return merged[:8]


def _normalize_text(value):
    normalized = ''.join(ch.lower() if ch.isalnum() else ' ' for ch in str(value or ''))
    return ' '.join(normalized.split())


def _book_key(title, author):
    return f"{_normalize_text(title)}::{_normalize_text((author or '').split(',')[0])}"


def _book_rank(row, query):
    title = _normalize_text(row.get('title'))
    author = _normalize_text(row.get('author'))
    query_norm = _normalize_text(query)
    score = 0
    if title == query_norm:
        score += 100
    elif title.startswith(query_norm):
        score += 55
    elif query_norm in title:
        score += 25
    if row.get('year'):
        score += 12
    if row.get('cover_url'):
        score += 10
    if row.get('isbn'):
        score += 8
    if author and author != 'unknown author':
        score += 6
    if ',' not in str(row.get('author') or ''):
        score += 4
    return score


def _genre_label(raw):
    if not raw:
        return ''
    clean = str(raw).replace('/', ' - ')
    parts = [part.strip() for part in clean.split('-') if part.strip()]
    if parts and parts[0].lower() == 'fiction' and len(parts) > 1:
        return f"Fiction - {parts[1]}"
    return parts[0] if parts else clean.strip()


def _best_isbn(values):
    normalized = []
    for value in values or []:
        if not value:
            continue
        isbn = str(value).replace('-', '').strip()
        if isbn:
            normalized.append(isbn)
    isbn_13 = next((isbn for isbn in normalized if len(isbn) == 13), '')
    return isbn_13 or (normalized[0] if normalized else '')


def _apply_known_book_metadata(row):
    overrides = {
        ('the grapes of wrath', 'john steinbeck'): {
            'isbn': '9780143039433',
            'year': '1939',
            'cover_url': _open_library_cover_url('9780143039433'),
            'genre': 'Fiction - Classics',
        },
        ('the fellowship of the ring', 'j r r tolkien'): {
            'isbn': '9780261103573',
            'year': '1954',
            'cover_url': _open_library_cover_url('9780261103573'),
            'genre': 'Fiction - Fantasy',
        },
        ('the fellowship of the ring', 'john ronald reuel tolkien'): {
            'isbn': '9780261103573',
            'year': '1954',
            'cover_url': _open_library_cover_url('9780261103573'),
            'genre': 'Fiction - Fantasy',
        },
    }
    author_key = _normalize_text((row.get('author') or '').split(',')[0])
    override = overrides.get((_normalize_text(row.get('title')), author_key))
    return {**row, **override} if override else row


def _search_books_google(query, max_results=8):
    resp = requests.get(
        'https://www.googleapis.com/books/v1/volumes',
        params={
            'q': f'intitle:{query}',
            'maxResults': max_results,
            'printType': 'books',
        },
        headers={'User-Agent': 'Readwoods/1.0 (+https://localhost)'},
        timeout=3.5,
    )

    if resp.status_code == 429:
        raise requests.HTTPError('Google Books rate-limited request', response=resp)
    resp.raise_for_status()

    data = resp.json()
    items = data.get('items', [])

    results = []
    for item in items:
        info = item.get('volumeInfo', {})
        title = (info.get('title') or '').strip()
        if not title:
            continue

        authors = info.get('authors') or []
        categories = info.get('categories') or []
        published = info.get('publishedDate') or ''
        year = (published[:4] if published else '')
        desc = info.get('description') or ''

        isbn_13 = ''
        isbn_10 = ''
        for ident in info.get('industryIdentifiers') or []:
            ident_type = ident.get('type')
            ident_value = (ident.get('identifier') or '').replace('-', '').strip()
            if ident_type == 'ISBN_13' and not isbn_13:
                isbn_13 = ident_value
            elif ident_type == 'ISBN_10' and not isbn_10:
                isbn_10 = ident_value
        isbn = isbn_13 or isbn_10

        image_links = info.get('imageLinks') or {}
        cover_url = image_links.get('thumbnail') or image_links.get('smallThumbnail') or ''
        if cover_url:
            cover_url = cover_url.replace('http://', 'https://').replace('&zoom=1', '&zoom=2')

        author_text = ', '.join(authors).strip() or 'Unknown author'
        has_author = 0 if author_text == 'Unknown author' else 1
        has_cover = 1 if cover_url else 0

        results.append({
            'title': title,
            'author': author_text,
            'genre': _genre_label(categories[0] if categories else ''),
            'year': year,
            'isbn': isbn,
            'isbn_options': [isbn_13, isbn_10],
            'cover_url': cover_url,
            'description': desc,
            '_score': has_cover * 4 + has_author * 2,
        })

    # Prefer suggestions with complete metadata (cover + author) and keep deterministic ordering.
    ranked = sorted(
        results,
        key=lambda r: (r.get('_score', 0), len(r.get('author', ''))),
        reverse=True,
    )
    cleaned = []
    for row in ranked:
        row.pop('_score', None)
        cleaned.append(row)

    return cleaned


def _search_books_open_library(query, max_results=8):
    resp = requests.get(
        'https://openlibrary.org/search.json',
        params={'title': query, 'limit': max_results},
        headers={'User-Agent': 'Readwoods/1.0 (+https://localhost)'},
        timeout=3.5,
    )
    resp.raise_for_status()

    data = resp.json()
    docs = data.get('docs') or []

    results = []
    for doc in docs:
        title = (doc.get('title') or '').strip()
        if not title:
            continue

        author_names = doc.get('author_name') or []
        author_text = ', '.join(author_names).strip() or 'Unknown author'
        subjects = doc.get('subject') or []
        publish_year = doc.get('first_publish_year')
        year = str(publish_year) if publish_year else ''

        isbn_values = doc.get('isbn') or []
        normalized_isbns = [s.replace('-', '').strip() for s in isbn_values if isinstance(s, str)]
        isbn = _best_isbn(normalized_isbns)

        cover_i = doc.get('cover_i')
        cover_url = f'https://covers.openlibrary.org/b/id/{cover_i}-L.jpg' if cover_i else ''

        results.append({
            'title': title,
            'author': author_text,
            'genre': _genre_label(subjects[0] if subjects else ''),
            'year': year,
            'isbn': isbn,
            'isbn_options': normalized_isbns,
            'cover_url': cover_url,
            'description': '',
        })

    return results


def _fetch_cover_google(title, author=''):
    try:
        q = f"intitle:{title}"
        if author:
            q += f"+inauthor:{author}"
        resp = requests.get(
            'https://www.googleapis.com/books/v1/volumes',
            params={'q': q, 'maxResults': 1},
            timeout=3,
        )
        data = resp.json()
        items = data.get('items', [])
        if items:
            links = items[0].get('volumeInfo', {}).get('imageLinks', {})
            raw_url = links.get('thumbnail') or links.get('smallThumbnail')
            if raw_url:
                # Force HTTPS and higher resolution
                return raw_url.replace('http://', 'https://').replace('&zoom=1', '&zoom=2')
    except Exception:
        pass
    return ''


def _fetch_cover_open_library(isbn):
    return _open_library_cover_url(isbn)


def _open_library_cover_url(isbn):
    normalized = (isbn or '').replace('-', '').strip()
    if not normalized:
        return ''
    return f"https://covers.openlibrary.org/b/isbn/{normalized}-L.jpg"


def _get_landing_recommendations(limit=6):
    cache_key = f'landing:recommendations:v3:{limit}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    tone_classes = [
        'book-card--gold',
        'book-card--teal',
        'book-card--orange',
        'book-card--rose',
        'book-card--blue',
        'book-card--green',
    ]

    curated = _curated_landing_books()
    random.shuffle(curated)
    picks = curated[:limit]

    for idx, book in enumerate(picks):
        book['tone'] = tone_classes[idx % len(tone_classes)]

    final_picks = picks[:limit]
    cache.set(cache_key, final_picks, timeout=60 * 10)
    return final_picks


def _curated_landing_books():
    books = [
        ('The Fellowship of the Ring', 'Fiction - Fantasy', 'J.R.R. Tolkien', '9780261103573', '1954', 'The first volume of The Lord of the Rings begins Frodo Baggins journey from the Shire.'),
        ('The Grapes of Wrath', 'Fiction - Classics', 'John Steinbeck', '9780143039433', '1939', 'A landmark novel about the Joad family migration during the Dust Bowl.'),
        ('Pride and Prejudice', 'Fiction - Classics', 'Jane Austen', '9780141439518', '1813', 'A sharp comedy of manners about Elizabeth Bennet, family, reputation, and love.'),
        ('Dune', 'Fiction - Science Fiction', 'Frank Herbert', '9780441172719', '1965', "A desert planet, a contested empire, and one of science fiction's most influential worlds."),
        ('Beloved', 'Fiction - Historical', 'Toni Morrison', '9781400033416', '1987', 'A haunting novel about memory, motherhood, and the afterlife of slavery.'),
        ('The Left Hand of Darkness', 'Fiction - Science Fiction', 'Ursula K. Le Guin', '9780441478125', '1969', 'A diplomatic mission to a frozen world becomes a study of culture, gender, and trust.'),
        ('The Hobbit', 'Fiction - Fantasy', 'J.R.R. Tolkien', '9780547928227', '1937', 'Bilbo Baggins leaves home for a dragon-guarded treasure and finds more courage than expected.'),
        ('Kindred', 'Fiction - Science Fiction', 'Octavia E. Butler', '9780807083697', '1979', 'A modern woman is pulled into the antebellum past in Butler powerful time-travel novel.'),
        ("The Handmaid's Tale", 'Fiction - Dystopian', 'Margaret Atwood', '9780385490818', '1985', 'A chilling speculative novel about power, gender, and resistance.'),
        ('The Name of the Wind', 'Fiction - Fantasy', 'Patrick Rothfuss', '9780756404741', '2007', 'Kvothe recounts the truth and legend behind his life as musician, magician, and fugitive.'),
        ('Station Eleven', 'Fiction - Literary', 'Emily St. John Mandel', '9780804172448', '2014', 'A post-pandemic novel about art, memory, and survival after collapse.'),
        ('The Fifth Season', 'Fiction - Fantasy', 'N. K. Jemisin', '9780316229296', '2015', 'A seismic fantasy about oppression, survival, and a world repeatedly ending.'),
    ]
    return [
        {
            'title': title,
            'genre': genre,
            'author': author,
            'cover_url': _open_library_cover_url(isbn),
            'isbn': isbn,
            'year': year,
            'description': description,
        }
        for title, genre, author, isbn, year, description in books
    ]


def _get_reading_content():
    items = [
        {
            'type': 'Article',
            'title': 'In a reading rut? How to get back into reading for fun',
            'source': 'The Guardian',
            'summary': 'Practical ways to make reading feel inviting again, from short sessions to better book choices.',
            'url': 'https://www.theguardian.com/wellness/2025/nov/17/how-to-start-reading-fun',
        },
        {
            'type': 'Article',
            'title': 'The Social Dilemma of E-Reading',
            'source': 'The New Yorker',
            'summary': 'A sharp look at what changes when private reading becomes a networked social experience.',
            'url': 'https://www.newyorker.com/books/page-turner/the-social-dilemma-of-e-reading',
        },
        {
            'type': 'Video',
            'title': 'Why should you read "Fahrenheit 451"?',
            'source': 'TED-Ed',
            'summary': 'A short animated introduction to Ray Bradbury and the power of forbidden books.',
            'url': 'https://www.youtube.com/watch?v=R9n98KChP3M',
        },
        {
            'type': 'Video',
            'title': 'The Danger of a Single Story',
            'source': 'TED',
            'summary': 'Chimamanda Ngozi Adichie on stories, perspective, and why literary variety matters.',
            'url': 'https://www.ted.com/talks/chimamanda_ngozi_adichie_the_danger_of_a_single_story',
        },
        {
            'type': 'Article',
            'title': 'Book Girl Summer: Why Brands Are Leaning into the Literary World',
            'source': 'Vogue',
            'summary': 'A visual culture piece on reading circles, books, and the renewed appeal of literary taste.',
            'url': 'https://www.vogue.com/article/book-girl-summer-why-brands-are-leaning-into-the-literary-world',
        },
        {
            'type': 'Video',
            'title': 'How fiction can change reality',
            'source': 'TED-Ed',
            'summary': 'Jessica Wise explains why stories can alter how people think and act.',
            'url': 'https://www.youtube.com/watch?v=ctaPAm14L10',
        },
    ]
    return [_with_content_image(item) for item in items]


def _with_content_image(item):
    enriched = dict(item)
    enriched['image_url'] = _resolve_content_image(item['url'])
    return enriched


def _resolve_content_image(url):
    cache_key = f"reading-content:image:v1:{url}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    image_url = _youtube_thumbnail(url) or _fetch_open_graph_image(url)
    cache.set(cache_key, image_url, timeout=60 * 60 * 24)
    return image_url


def _youtube_thumbnail(url):
    match = re.search(r'(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,})', url)
    if not match:
        return ''
    video_id = match.group(1)
    return f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'


def _fetch_open_graph_image(url):
    try:
        resp = requests.get(
            url,
            headers={'User-Agent': 'Readwoods/1.0 (+https://localhost)'},
            timeout=2.5,
        )
        resp.raise_for_status()
        html = resp.text[:120000]
        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, flags=re.IGNORECASE)
            if match:
                image_url = unescape(match.group(1).strip())
                if image_url.startswith('//'):
                    return f'https:{image_url}'
                if image_url.startswith('/'):
                    origin = re.match(r'https?://[^/]+', url)
                    return f"{origin.group(0)}{image_url}" if origin else ''
                return image_url
    except Exception:
        logger.debug('Could not fetch content image for %s', url, exc_info=True)
    return ''
