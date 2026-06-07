import requests
import logging
import csv
import hashlib
import io
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import random
import re
from smtplib import SMTPException
from requests import RequestException
from html import unescape
from django.contrib.auth.models import User
from django.db import transaction
from django.db import IntegrityError
from django.db.models import Q, Count, Sum
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

from .models import (
    Node, Edge, FriendRequest, Friendship, CommunityPost, ImportedBook, BookReview,
    Tree, TreeVersion, ReadingChallenge, DailyPageLog,
)
from .serializers import NodeSerializer, EdgeSerializer, ImportedBookSerializer, TreeSerializer, TreeVersionSerializer, BookReviewSerializer
from .forms import EmailUserCreationForm


logger = logging.getLogger(__name__)
AUTO_TREE_MAX_BOOKS = 15


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
    current_tree = _get_tree_from_request(request)
    trees = Tree.objects.filter(user=request.user).annotate(node_count=Count('nodes'))
    return render(request, 'tree.html', {
        'trees': trees,
        'current_tree': current_tree,
        'tree_owner': request.user,
        'is_readonly_tree': False,
    })


@login_required
def shared_tree_page(request, username, tree_id):
    owner = get_object_or_404(User, username=username)
    tree = get_object_or_404(Tree, pk=tree_id, user=owner)
    if not _can_view_tree(request.user, tree):
        return redirect('tree:community-feed')
    return render(request, 'tree.html', {
        'trees': [tree],
        'current_tree': tree,
        'tree_owner': owner,
        'is_readonly_tree': owner.id != request.user.id,
        'shared_tree_api_url': reverse('tree:api-shared-tree', args=[owner.username, tree.id]),
    })


@login_required
def my_books(request):
    current_tree = _get_tree_from_request(request)
    tree_parent_options = Node.objects.filter(user=request.user, tree=current_tree).order_by('node_type', 'title')
    trees = Tree.objects.filter(user=request.user).annotate(node_count=Count('nodes'))
    books = sorted(
        _get_library_books(request.user),
        key=lambda book: (book.title or '').lower(),
    )
    reviews = _reviews_by_book_identity(request.user)
    reviewed_books = BookReview.objects.filter(user=request.user).order_by('-updated_at')
    for book in books:
        setattr(book, 'user_review', _review_for_book_from_map(reviews, book))
    shelf_counter = Counter(book.shelf for book in books)
    shelf_counts = {
        'all': len(books),
        Node.SHELF_WANT_TO_READ: shelf_counter[Node.SHELF_WANT_TO_READ],
        Node.SHELF_CURRENTLY_READING: shelf_counter[Node.SHELF_CURRENTLY_READING],
        Node.SHELF_READ: shelf_counter[Node.SHELF_READ],
        Node.SHELF_DID_NOT_FINISH: shelf_counter[Node.SHELF_DID_NOT_FINISH],
    }
    custom_counts = Counter(book.custom_shelf for book in books if book.custom_shelf)
    custom_shelves = [
        {'custom_shelf': name, 'total': total}
        for name, total in sorted(custom_counts.items(), key=lambda item: item[0].lower())
    ]
    return render(request, 'my_books.html', {
        'books': books,
        'tree_parent_options': tree_parent_options,
        'shelf_choices': Node.SHELF_CHOICES,
        'shelf_counts': shelf_counts,
        'custom_shelves': custom_shelves,
        'trees': trees,
        'current_tree': current_tree,
        'reviews': reviews,
        'reviewed_books': reviewed_books,
    })


@login_required
def challenges(request):
    context = _challenge_context(request.user)
    return render(request, 'challenges.html', context)


def _challenge_context(user):
    challenge, _ = ReadingChallenge.objects.get_or_create(user=user, year=2026)
    node_read_books = Node.objects.filter(
        user=user,
        node_type='book',
        shelf=Node.SHELF_READ,
        date_read__year=challenge.year,
    )
    books_read = (
        len([book for book in node_read_books if not _is_library_shadow(book)])
        + ImportedBook.objects.filter(
            user=user,
            shelf=Node.SHELF_READ,
            date_read__year=challenge.year,
        ).count()
    )
    target = max(challenge.target_books, 1)
    book_percent = min(100, round((books_read / target) * 100))

    page_days = _page_streak_days(user)
    current_streak = _current_page_streak(page_days)
    best_streak = _best_page_streak(page_days)
    recent_logs = DailyPageLog.objects.filter(user=user).order_by('-log_date', '-created_at')[:8]
    currently_reading = [
        book for book in Node.objects.filter(
            user=user,
            node_type='book',
            shelf=Node.SHELF_CURRENTLY_READING,
        ).order_by('title')
        if not _is_library_shadow(book)
    ][:8]
    currently_reading += list(ImportedBook.objects.filter(
        user=user,
        shelf=Node.SHELF_CURRENTLY_READING,
    ).order_by('title')[:8])

    return {
        'challenge': challenge,
        'books_read_2026': books_read,
        'book_percent': book_percent,
        'books_remaining': max(target - books_read, 0),
        'current_page_streak': current_streak,
        'best_page_streak': best_streak,
        'page_streak_goal': 50,
        'recent_page_logs': recent_logs,
        'currently_reading_books': currently_reading[:8],
    }


def _challenge_payload(user):
    context = _challenge_context(user)
    challenge = context['challenge']
    return {
        'challenge': {
            'year': challenge.year,
            'target_books': challenge.target_books,
        },
        'books_read_2026': context['books_read_2026'],
        'book_percent': context['book_percent'],
        'books_remaining': context['books_remaining'],
        'current_page_streak': context['current_page_streak'],
        'best_page_streak': context['best_page_streak'],
        'page_streak_goal': context['page_streak_goal'],
    }


def _page_streak_days(user):
    rows = (
        DailyPageLog.objects
        .filter(user=user)
        .values('log_date')
        .annotate(total_pages=Sum('pages'))
        .filter(total_pages__gte=50)
        .order_by('log_date')
    )
    return {row['log_date'] for row in rows}


def _current_page_streak(days):
    if not days:
        return 0
    cursor = date.today()
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _best_page_streak(days):
    if not days:
        return 0
    best = 0
    current = 0
    previous = None
    for day in sorted(days):
        if previous and day == previous + timedelta(days=1):
            current += 1
        else:
            current = 1
        best = max(best, current)
        previous = day
    return best


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


def _are_friends(user, other_user):
    if not user.is_authenticated or user.id == other_user.id:
        return user.is_authenticated
    return Friendship.objects.filter(
        Q(user_a=user, user_b=other_user) | Q(user_a=other_user, user_b=user)
    ).exists()


def _can_view_tree(user, tree):
    if user.is_authenticated and tree.user_id == user.id:
        return True
    if tree.visibility == Tree.VISIBILITY_PUBLIC:
        return True
    if tree.visibility == Tree.VISIBILITY_FRIENDS:
        return _are_friends(user, tree.user)
    return False


def _get_display_name(user):
    profile = getattr(user, 'profile', None)
    if profile and profile.display_name:
        return profile.display_name
    return user.username


def _get_or_create_default_tree(user):
    tree = Tree.objects.filter(user=user, is_default=True).order_by('created_at').first()
    if tree:
        return tree
    tree = Tree.objects.filter(user=user).order_by('created_at').first()
    if tree:
        if not tree.is_default:
            tree.is_default = True
            tree.save(update_fields=['is_default', 'updated_at'])
        return tree
    return Tree.objects.create(user=user, name='Main Tree', is_default=True)


def _get_tree_by_id_or_default(user, tree_id=None):
    if tree_id:
        return get_object_or_404(Tree.objects.filter(user=user), pk=tree_id)
    return _get_or_create_default_tree(user)


def _get_tree_from_request(request):
    tree_id = request.GET.get('tree') or request.GET.get('tree_id') or request.POST.get('tree_id')
    if not tree_id and hasattr(request, 'data'):
        tree_id = request.data.get('tree_id') or request.data.get('tree')
    return _get_tree_by_id_or_default(request.user, tree_id)


def _tree_query(request):
    tree = _get_tree_from_request(request)
    return tree, {'tree_id': tree.id}


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
        'submit_label': 'Publish Post',
        'cancel_url': reverse('tree:community-feed'),
    })


@login_required
def community_edit_post(request, post_id):
    post = get_object_or_404(CommunityPost, pk=post_id, user=request.user)
    errors = []
    payload = {
        'title': post.title,
        'content': post.content,
        'progress_status': post.progress_status,
        'visibility': post.visibility,
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

        valid_statuses = {value for value, _ in CommunityPost.STATUS_CHOICES}
        valid_visibilities = {value for value, _ in CommunityPost.VISIBILITY_CHOICES}
        if payload['progress_status'] and payload['progress_status'] not in valid_statuses:
            errors.append('Please choose a valid progress status.')
        if payload['visibility'] not in valid_visibilities:
            errors.append('Please choose a valid visibility.')

        if not errors:
            post.title = payload['title']
            post.content = payload['content']
            post.progress_status = payload['progress_status']
            post.visibility = payload['visibility']
            post.save(update_fields=['title', 'content', 'progress_status', 'visibility', 'updated_at'])
            return redirect('tree:community-my-posts')

    return render(request, 'community_create_post.html', {
        'errors': errors,
        'form': payload,
        'status_choices': CommunityPost.STATUS_CHOICES,
        'visibility_choices': CommunityPost.VISIBILITY_CHOICES,
        'is_editing': True,
        'submit_label': 'Save Changes',
        'cancel_url': reverse('tree:community-my-posts'),
    })


@login_required
@require_http_methods(['POST'])
def community_delete_post(request, post_id):
    post = get_object_or_404(CommunityPost, pk=post_id, user=request.user)
    post.delete()
    return redirect('tree:community-my-posts')


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
    tree = _get_tree_from_request(request)
    cache_key = f'tree-data:v2:user:{request.user.id}:tree:{tree.id}'
    cached = cache.get(cache_key)
    if cached:
        return Response(cached)

    nodes = Node.objects.filter(user=request.user, tree=tree).annotate(children_count=Count('children'))
    edges = Edge.objects.select_related('source', 'target').filter(user=request.user, tree=tree)

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

    payload = {'tree': TreeSerializer(tree).data, 'nodes': node_data, 'edges': edge_data}
    cache.set(cache_key, payload, timeout=60)
    return Response(payload)


# ──────────────────────────────────────────────
# Node CRUD
# ──────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def shared_tree_data(request, username, tree_id):
    owner = get_object_or_404(User, username=username)
    tree = get_object_or_404(Tree, pk=tree_id, user=owner)
    if not _can_view_tree(request.user, tree):
        return Response({'detail': 'You do not have access to this tree.'}, status=status.HTTP_403_FORBIDDEN)

    nodes = Node.objects.filter(user=owner, tree=tree).annotate(children_count=Count('children'))
    edges = Edge.objects.select_related('source', 'target').filter(user=owner, tree=tree)
    node_data = NodeSerializer(nodes, many=True, context={'request': request}).data
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
    return Response({'tree': TreeSerializer(tree).data, 'nodes': node_data, 'edges': edge_data})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def node_list(request):
    tree = _get_tree_from_request(request)
    if request.method == 'GET':
        nodes = Node.objects.filter(user=request.user, tree=tree).annotate(children_count=Count('children'))
        serializer = NodeSerializer(nodes, many=True, context={'request': request})
        return Response(serializer.data)

    payload = dict(request.data)
    payload.setdefault('tree', tree.id)
    serializer = NodeSerializer(data=payload, context={'request': request})
    if serializer.is_valid():
        node = serializer.save(user=request.user, tree=tree)
        # Auto-fetch cover if not supplied
        if node.node_type != 'book':
            pass
        elif not node.cover_image and node.isbn:
            node.cover_image = _fetch_cover_open_library(node.isbn)
            node.save(update_fields=['cover_image'])
        elif not node.cover_image and node.title:
            node.cover_image = _fetch_cover_google(node.title, node.author)
            node.save(update_fields=['cover_image'])
        _invalidate_tree_cache(request.user.id, tree.id)
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
            _invalidate_tree_cache(request.user.id, node.tree_id)
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    node.delete()
    _invalidate_tree_cache(request.user.id, node.tree_id)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def edge_list(request):
    tree = _get_tree_from_request(request)
    if request.method == 'GET':
        edges = Edge.objects.filter(user=request.user, tree=tree)
        serializer = EdgeSerializer(edges, many=True)
        return Response(serializer.data)

    payload = dict(request.data)
    payload.setdefault('tree', tree.id)
    serializer = EdgeSerializer(data=payload)
    if serializer.is_valid():
        source = serializer.validated_data['source']
        target = serializer.validated_data['target']
        edge_type = serializer.validated_data.get('edge_type', 'custom')

        if source.user_id != request.user.id or target.user_id != request.user.id:
            return Response(
                {'detail': 'Source and target must belong to the current user.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if source.tree_id != tree.id or target.tree_id != tree.id:
            return Response(
                {'detail': 'Source and target must belong to the selected tree.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if source.id == target.id:
            return Response(
                {'detail': 'Source and target must be different nodes.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if Edge.objects.filter(
            user=request.user,
            tree=tree,
            source=source,
            target=target,
            edge_type=edge_type,
        ).exists():
            return Response(
                {'detail': 'This connection already exists.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        edge = serializer.save(user=request.user, tree=tree)
        _invalidate_tree_cache(request.user.id, tree.id)
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
            _invalidate_tree_cache(request.user.id, edge.tree_id)
            return Response(EdgeSerializer(saved).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    edge.delete()
    _invalidate_tree_cache(request.user.id, edge.tree_id)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def book_review_list_create(request):
    if request.method == 'GET':
        reviews = _review_queryset_for_request(request)
        return Response(BookReviewSerializer(reviews, many=True).data)

    title = (request.data.get('title') or '').strip()[:255]
    author = (request.data.get('author') or '').strip()[:255]
    isbn = _normalize_goodreads_isbn(request.data.get('isbn'))[:20]
    review_text = (request.data.get('review') or '').strip()
    if not title:
        return Response({'detail': 'Book title is required.'}, status=status.HTTP_400_BAD_REQUEST)
    if not review_text:
        return Response({'detail': 'Review is required.'}, status=status.HTTP_400_BAD_REQUEST)

    node = _optional_user_node(request.user, request.data.get('node'))
    imported_book = _optional_imported_book(request.user, request.data.get('imported_book'))
    rating = _safe_float(request.data.get('rating'))
    lookup = _review_lookup(request.user, title, author, isbn, node, imported_book)
    defaults = {
        'node': node,
        'imported_book': imported_book,
        'title': title,
        'author': author,
        'isbn': isbn,
        'cover_image': (request.data.get('cover_image') or '').strip()[:1000],
        'rating': rating,
        'review': review_text,
    }
    review, _ = BookReview.objects.update_or_create(defaults=defaults, **lookup)
    return Response(BookReviewSerializer(review).data, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def book_review_detail(request, review_id):
    review = get_object_or_404(BookReview, pk=review_id, user=request.user)
    review.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


def _invalidate_tree_cache(user_id, tree_id=None):
    if tree_id:
        cache.delete(f'tree-data:v2:user:{user_id}:tree:{tree_id}')
    cache.delete(f'tree-data:v1:user:{user_id}')


def _optional_user_node(user, node_id):
    if not node_id:
        return None
    return get_object_or_404(Node.objects.filter(user=user), pk=node_id)


def _optional_imported_book(user, book_id):
    if not book_id:
        return None
    return get_object_or_404(ImportedBook.objects.filter(user=user), pk=book_id)


def _review_lookup(user, title, author, isbn, node=None, imported_book=None):
    if node:
        return {'user': user, 'node': node}
    if imported_book:
        return {'user': user, 'imported_book': imported_book}
    if isbn:
        return {'user': user, 'isbn': isbn}
    return {'user': user, 'title': title, 'author': author}


def _review_queryset_for_request(request):
    reviews = BookReview.objects.filter(user=request.user)
    node_id = request.query_params.get('node')
    imported_id = request.query_params.get('imported_book')
    isbn = _normalize_goodreads_isbn(request.query_params.get('isbn'))
    title = (request.query_params.get('title') or '').strip()
    author = (request.query_params.get('author') or '').strip()
    if node_id:
        return reviews.filter(node_id=node_id)
    if imported_id:
        return reviews.filter(imported_book_id=imported_id)
    if isbn:
        return reviews.filter(isbn=isbn)
    if title:
        reviews = reviews.filter(title__iexact=title)
        if author:
            reviews = reviews.filter(author__iexact=author)
        return reviews
    return reviews


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def tree_list(request):
    if request.method == 'GET':
        trees = Tree.objects.filter(user=request.user).annotate(node_count=Count('nodes'))
        return Response(TreeSerializer(trees, many=True).data)

    name = (request.data.get('name') or '').strip()[:160]
    if not name:
        return Response({'detail': 'Tree name is required.'}, status=status.HTTP_400_BAD_REQUEST)
    tree = Tree.objects.create(
        user=request.user,
        name=name,
        description=(request.data.get('description') or '').strip()[:280],
    )
    return Response(TreeSerializer(tree).data, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def tree_detail(request, tree_id):
    tree = get_object_or_404(Tree.objects.filter(user=request.user), pk=tree_id)
    was_default = tree.is_default
    deleted_tree_id = tree.id
    tree.delete()

    next_tree = Tree.objects.filter(user=request.user).order_by('-is_default', 'created_at').first()
    if next_tree and (was_default or not Tree.objects.filter(user=request.user, is_default=True).exists()):
        if not next_tree.is_default:
            next_tree.is_default = True
            next_tree.save(update_fields=['is_default', 'updated_at'])

    _invalidate_tree_cache(request.user.id, deleted_tree_id)
    return Response({
        'detail': 'Tree deleted.',
        'next_tree_id': next_tree.id if next_tree else None,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tree_auto_from_shelf(request):
    shelf = (request.data.get('shelf') or '').strip()
    shelf_type = (request.data.get('shelf_type') or 'custom').strip().lower()
    mode = (request.data.get('mode') or 'author').strip().lower()
    destination = (request.data.get('destination') or 'new').strip().lower()

    if not shelf:
        return Response({'detail': 'Choose a shelf first.'}, status=status.HTTP_400_BAD_REQUEST)

    books = _get_library_books_for_shelf(request.user, shelf, shelf_type)
    if not books:
        return Response({'detail': 'No books were found on this shelf.'}, status=status.HTTP_400_BAD_REQUEST)
    if len(books) > AUTO_TREE_MAX_BOOKS:
        return Response(
            {
                'detail': f'Auto tree generation supports up to {AUTO_TREE_MAX_BOOKS} books at a time.',
                'book_count': len(books),
                'max_books': AUTO_TREE_MAX_BOOKS,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    strategy = _auto_tree_strategy(mode)
    if strategy is None:
        return Response({'detail': 'This tree grouping mode is not available yet.'}, status=status.HTTP_400_BAD_REQUEST)

    if destination == 'existing':
        tree = _get_tree_by_id_or_default(request.user, request.data.get('tree_id') or request.data.get('tree'))
    else:
        tree_name = (request.data.get('tree_name') or f'{shelf} authors').strip()[:160]
        tree = Tree.objects.create(
            user=request.user,
            name=tree_name or 'Auto Tree',
            description=f'Auto-created from shelf: {shelf}'[:280],
        )

    with transaction.atomic():
        _create_tree_version(request.user, tree, f'Before auto tree from {shelf}', 'auto_tree')
        result = strategy.generate(request.user, books, tree)

    result['tree'] = TreeSerializer(tree).data
    _invalidate_tree_cache(request.user.id, tree.id)
    return Response(result, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_books_recommendations(request):
    recommendations = _get_user_book_recommendations(request.user)
    return Response({'results': recommendations})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tree_version_list(request):
    tree = _get_tree_from_request(request)
    versions = TreeVersion.objects.filter(user=request.user, tree=tree)[:20]
    return Response(TreeVersionSerializer(versions, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tree_version_create(request):
    tree = _get_tree_from_request(request)
    label = (request.data.get('label') or '').strip()[:180]
    comment = (request.data.get('comment') or '').strip()[:2000]
    visibility = (request.data.get('visibility') or tree.visibility or Tree.VISIBILITY_PRIVATE).strip()
    post_to_community = bool(request.data.get('post_to_community'))
    if not label:
        label = 'Saved tree version'
    valid_visibilities = {value for value, _ in Tree.VISIBILITY_CHOICES}
    if visibility not in valid_visibilities:
        return Response({'detail': 'Choose a valid tree visibility.'}, status=status.HTTP_400_BAD_REQUEST)
    if tree.visibility != visibility:
        tree.visibility = visibility
        tree.save(update_fields=['visibility', 'updated_at'])
    version = _create_tree_version(request.user, tree, label, 'manual_save', comment=comment)
    if post_to_community and comment:
        CommunityPost.objects.create(
            user=request.user,
            tree=tree,
            tree_version=version,
            title=f'Updated tree: {tree.name}',
            content=comment,
            progress_status=CommunityPost.STATUS_READING,
            visibility=visibility if visibility != Tree.VISIBILITY_PRIVATE else CommunityPost.VISIBILITY_PRIVATE,
        )
    return Response(TreeVersionSerializer(version).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tree_version_restore(request, version_id):
    tree = _get_tree_from_request(request)
    version = get_object_or_404(TreeVersion, pk=version_id, user=request.user, tree=tree)
    _create_tree_version(request.user, tree, 'Before restoring tree version', 'restore')
    _restore_tree_snapshot(request.user, tree, version.snapshot or {})
    _invalidate_tree_cache(request.user.id, tree.id)
    return Response({'detail': 'Tree version restored.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tree_snapshot_restore(request):
    tree = _get_tree_from_request(request)
    snapshot = request.data.get('snapshot') or {}
    if not isinstance(snapshot, dict):
        return Response({'detail': 'Snapshot must be an object.'}, status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        _restore_tree_snapshot(request.user, tree, snapshot)
    _invalidate_tree_cache(request.user.id, tree.id)
    return Response({'detail': 'Tree changes discarded.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def challenge_target_update(request):
    raw_target = request.data.get('target_books')
    try:
        target = int(raw_target)
    except (TypeError, ValueError):
        return Response({'detail': 'Target must be a number.'}, status=status.HTTP_400_BAD_REQUEST)
    if target < 1 or target > 1000:
        return Response({'detail': 'Choose a target between 1 and 1000 books.'}, status=status.HTTP_400_BAD_REQUEST)

    challenge, _ = ReadingChallenge.objects.get_or_create(
        user=request.user,
        year=2026,
        defaults={'target_books': target},
    )
    if challenge.target_books != target:
        challenge.target_books = target
        challenge.save(update_fields=['target_books', 'updated_at'])
    return Response(_challenge_payload(request.user))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reading_update_create(request):
    source = (request.data.get('source') or '').strip()
    book_id = request.data.get('book_id')
    try:
        pages = int(request.data.get('pages'))
    except (TypeError, ValueError):
        return Response({'detail': 'Pages must be a number.'}, status=status.HTTP_400_BAD_REQUEST)
    if pages < 1 or pages > 5000:
        return Response({'detail': 'Enter pages between 1 and 5000.'}, status=status.HTTP_400_BAD_REQUEST)

    raw_date = (request.data.get('log_date') or '').strip()
    try:
        log_date = date.fromisoformat(raw_date) if raw_date else date.today()
    except ValueError:
        return Response({'detail': 'Use a valid reading date.'}, status=status.HTTP_400_BAD_REQUEST)

    node = None
    imported_book = None
    if source == 'imported':
        imported_book = get_object_or_404(ImportedBook.objects.filter(user=request.user), pk=book_id)
        book = imported_book
    else:
        node = get_object_or_404(Node.objects.filter(user=request.user, node_type='book'), pk=book_id)
        book = node

    if book.shelf != Node.SHELF_CURRENTLY_READING:
        return Response(
            {'detail': 'Page streak updates are only available for Currently Reading books.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    DailyPageLog.objects.create(
        user=request.user,
        node=node,
        imported_book=imported_book,
        book_title=book.title,
        book_author=book.author,
        log_date=log_date,
        pages=pages,
    )
    return Response(_challenge_payload(request.user), status=status.HTTP_201_CREATED)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def imported_book_detail(request, pk):
    imported_book = get_object_or_404(ImportedBook.objects.filter(user=request.user), pk=pk)

    if request.method == 'PATCH':
        serializer = ImportedBookSerializer(imported_book, data=request.data, partial=True)
        if serializer.is_valid():
            saved = serializer.save()
            return Response(ImportedBookSerializer(saved).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    imported_book.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def imported_book_add_to_tree(request, pk):
    imported_book = get_object_or_404(ImportedBook.objects.filter(user=request.user), pk=pk)
    tree = _get_tree_from_request(request)
    parent_id = request.data.get('parent') or None
    parent = None
    if parent_id:
        parent = get_object_or_404(Node.objects.filter(user=request.user, tree=tree), pk=parent_id)

    existing_node = _find_existing_tree_book(request.user, {
        'title': imported_book.title,
        'author': imported_book.author,
        'isbn': imported_book.isbn,
    }, tree=tree)
    if existing_node:
        serializer = NodeSerializer(
            existing_node,
            data={'parent': str(parent.id) if parent else None, 'pos_x': None, 'pos_y': None},
            partial=True,
            context={'request': request},
        )
        if serializer.is_valid():
            saved = serializer.save()
            _invalidate_tree_cache(request.user.id, tree.id)
            return Response(NodeSerializer(saved, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    node = Node.objects.create(
        user=request.user,
        tree=tree,
        node_type='book',
        title=imported_book.title,
        author=imported_book.author,
        year=imported_book.year,
        rating=imported_book.rating,
        isbn=imported_book.isbn,
        cover_image=imported_book.cover_image,
        parent=parent,
        shelf=imported_book.shelf,
        custom_shelf=imported_book.custom_shelf,
        date_read=imported_book.date_read,
        notes=imported_book.notes,
    )
    _invalidate_tree_cache(request.user.id, tree.id)
    return Response(NodeSerializer(node, context={'request': request}).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def library_book_create(request):
    """Add a searched book to My Books without placing it on the tree."""
    book = _clean_import_payload(request.data or {})
    if not book['title']:
        return Response({'detail': 'Choose a book before adding it.'}, status=status.HTTP_400_BAD_REQUEST)

    existing = _find_existing_book(request.user, book)
    if existing:
        source = getattr(existing, 'library_source', 'tree')
        return Response(
            {
                'detail': 'This book is already in My Books.',
                'existing_id': str(existing.id),
                'source': source,
            },
            status=status.HTTP_409_CONFLICT,
        )

    source_key = book.get('source_key') or _book_key(book['title'], book.get('author'))
    imported_book = ImportedBook.objects.create(
        user=request.user,
        source=ImportedBook.SOURCE_SEARCH,
        source_key=source_key[:160],
        title=book['title'],
        author=book.get('author') or '',
        year=book.get('year'),
        rating=book.get('rating'),
        isbn=book.get('isbn') or '',
        cover_image=book.get('cover_image') or '',
        shelf=book.get('shelf') or Node.SHELF_WANT_TO_READ,
        custom_shelf=book.get('custom_shelf') or '',
        notes=book.get('notes') or '',
    )
    return Response(ImportedBookSerializer(imported_book).data, status=status.HTTP_201_CREATED)


def _auto_tree_strategy(mode):
    strategies = {
        'author': AuthorAutoTreeStrategy(),
    }
    return strategies.get(mode)


class AuthorAutoTreeStrategy:
    mode = 'author'

    def generate(self, user, books, tree):
        created_author_count = 0
        reused_author_count = 0
        created_book_count = 0
        reused_book_count = 0
        connected_count = 0
        skipped = []
        author_payloads = self._author_payloads(books)

        for index, source_book in enumerate(books):
            source_payload = _library_book_to_payload(source_book)
            enriched_book = _enrich_book_for_auto_tree(source_payload, allow_network=False)
            authors = _split_author_names(enriched_book.get('author') or source_payload.get('author'))
            if not authors:
                skipped.append({
                    'title': source_payload.get('title') or 'Untitled',
                    'reason': 'No author was found.',
                })
                continue

            author_nodes = []
            for author_name in authors:
                author_payload = author_payloads.get(_normalize_text(author_name)) or _enrich_author_for_auto_tree(author_name, allow_network=False)
                author_node, created = _get_or_create_author_node(user, tree, author_payload, index)
                author_nodes.append(author_node)
                if created:
                    created_author_count += 1
                else:
                    reused_author_count += 1

            primary_author = author_nodes[0]
            book_node, created = _get_or_create_tree_book_from_library(
                user,
                tree,
                enriched_book,
                source_book,
                primary_author,
                index,
            )
            if created:
                created_book_count += 1
            else:
                reused_book_count += 1

            for author_node in author_nodes[1:]:
                _, edge_created = Edge.objects.get_or_create(
                    user=user,
                    tree=tree,
                    source=author_node,
                    target=book_node,
                    edge_type='author',
                    defaults={
                        'label': f'{author_node.title} wrote {book_node.title}',
                        'style': {
                            'color': '#c4b5fd',
                            'line_style': 'dash-dot',
                            'width': 3,
                        },
                    },
                )
                if edge_created:
                    connected_count += 1

        return {
            'mode': self.mode,
            'book_count': len(books),
            'created_authors': created_author_count,
            'reused_authors': reused_author_count,
            'created_books': created_book_count,
            'reused_books': reused_book_count,
            'created_edges': connected_count,
            'skipped': skipped,
        }

    def _author_payloads(self, books):
        payloads = {}
        for source_book in books:
            source_payload = _library_book_to_payload(source_book)
            for author_name in _split_author_names(source_payload.get('author')):
                key = _normalize_text(author_name)
                if key in payloads:
                    continue
                payloads[key] = _enrich_author_for_auto_tree(author_name, allow_network=True)
        return payloads


def _get_library_books(user):
    imported_books = list(ImportedBook.objects.filter(user=user).order_by('date_added'))
    tree_books = list(
        Node.objects
        .filter(user=user, node_type='book')
        .order_by('date_added')
    )
    tree_books = [book for book in tree_books if not _is_library_shadow(book)]
    return _dedupe_library_books(imported_books + tree_books)


def _reviews_by_book_identity(user):
    reviews = {}
    for review in BookReview.objects.filter(user=user).order_by('-updated_at'):
        keys = [
            review.isbn and f'isbn:{review.isbn}',
            f'title:{_normalize_text(review.title)}:{_normalize_text(review.author)}',
        ]
        for key in keys:
            if key and key not in reviews:
                reviews[key] = review
    return reviews


def _review_for_book_from_map(reviews, book):
    isbn = _normalize_goodreads_isbn(getattr(book, 'isbn', ''))
    if isbn and f'isbn:{isbn}' in reviews:
        return reviews[f'isbn:{isbn}']
    key = f"title:{_normalize_text(getattr(book, 'title', ''))}:{_normalize_text(getattr(book, 'author', ''))}"
    return reviews.get(key)


def _is_library_shadow(book):
    style = getattr(book, 'style', None) or {}
    return bool(style.get('library_shadow'))


def _get_library_books_for_shelf(user, shelf, shelf_type):
    shelf_norm = _normalize_text(shelf)
    valid_shelves = {value for value, _ in Node.SHELF_CHOICES}
    books = _get_library_books(user)

    if shelf_type == 'all' or shelf_norm == 'all':
        return _dedupe_library_books(books)
    if shelf_type == 'standard' or shelf in valid_shelves:
        return _dedupe_library_books([book for book in books if book.shelf == shelf])
    return _dedupe_library_books([
        book for book in books
        if _normalize_text(getattr(book, 'custom_shelf', '')) == shelf_norm
    ])


def _dedupe_library_books(books):
    deduped = []
    seen = set()
    for book in books:
        key = _library_book_identity(book)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(book)
    return deduped


def _library_book_identity(book):
    isbn = _normalize_goodreads_isbn(getattr(book, 'isbn', ''))
    if isbn:
        return f'isbn:{isbn}'
    return _book_key(getattr(book, 'title', ''), getattr(book, 'author', ''))


def _library_book_to_payload(book):
    return {
        'title': book.title,
        'author': book.author,
        'genre': getattr(book, 'genre', ''),
        'series': getattr(book, 'series', ''),
        'year': book.year,
        'rating': book.rating,
        'isbn': book.isbn,
        'cover_image': getattr(book, 'cover_image', ''),
        'description': getattr(book, 'description', '') or getattr(book, 'notes', ''),
        'notes': getattr(book, 'notes', ''),
        'shelf': book.shelf,
        'custom_shelf': book.custom_shelf,
        'date_read': book.date_read,
    }


def _split_author_names(author_value):
    author_text = str(author_value or '').strip()
    if not author_text or author_text.lower() == 'unknown author':
        return []
    pieces = re.split(r'\s+(?:and|&)\s+|;', author_text)
    authors = []
    for piece in pieces:
        for value in str(piece or '').split(','):
            cleaned = value.strip()
            if cleaned and _normalize_text(cleaned) not in {'unknown author', 'author'}:
                authors.append(cleaned[:255])
    seen = set()
    unique = []
    for author in authors:
        key = _normalize_text(author)
        if key in seen:
            continue
        seen.add(key)
        unique.append(author)
    return unique


def _enrich_book_for_auto_tree(book, allow_network=False):
    title = book.get('title') or ''
    author = book.get('author') or ''
    query = f'{title} {author}'.strip()
    if len(query) < 2:
        return book

    cache_key = _cache_key('auto-tree:book:v1', query.lower())
    cached = cache.get(cache_key)
    if cached is None:
        if not allow_network:
            return book
        cached = _safe_external_lookup(
            lambda: _search_books_combined(query)[:4],
            'Auto tree book lookup failed for query=%r',
            query,
        )
        cache.set(cache_key, cached, timeout=60 * 60 * 24)

    best = _best_catalog_match(book, cached)
    if not best:
        return book
    return {
        **book,
        'title': best.get('title') or book.get('title') or '',
        'author': best.get('author') or book.get('author') or '',
        'genre': best.get('genre') or book.get('genre') or '',
        'year': _safe_int(best.get('year')) or book.get('year'),
        'isbn': best.get('isbn') or book.get('isbn') or '',
        'cover_image': best.get('cover_url') or best.get('cover_image') or book.get('cover_image') or '',
        'description': best.get('description') or book.get('description') or '',
    }


def _best_catalog_match(book, candidates):
    if not candidates:
        return None
    title = _normalize_text(book.get('title'))
    author = _normalize_text(book.get('author'))
    isbn = _normalize_goodreads_isbn(book.get('isbn'))
    ranked = []
    for candidate in candidates:
        score = 0
        if isbn and _normalize_goodreads_isbn(candidate.get('isbn')) == isbn:
            score += 100
        if title and _normalize_text(candidate.get('title')) == title:
            score += 80
        if author and _normalize_text(candidate.get('author')) == author:
            score += 50
        score += _book_rank(candidate, f"{book.get('title') or ''} {book.get('author') or ''}")
        ranked.append((score, candidate))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1] if ranked and ranked[0][0] > 0 else candidates[0]


def _enrich_author_for_auto_tree(author_name, allow_network=False):
    payload = {
        'title': author_name,
        'author': 'Author',
        'node_type': 'author',
        'year': None,
        'cover_url': '',
        'description': '',
    }
    cache_key = _cache_key('auto-tree:author:v1', author_name.lower())
    cached = cache.get(cache_key)
    if cached is None:
        cached = cache.get(_cache_key('author-search:v1', author_name.lower()))
    if cached is None or (allow_network and cached == []):
        if not allow_network:
            return payload
        cached = _safe_external_lookup(
            lambda: _search_authors_open_library(author_name, timeout=1.2)[:3],
            'Auto tree author lookup failed for query=%r',
            author_name,
        )
        cache.set(cache_key, cached, timeout=60 * 60 * 24 if cached else 60 * 5)

    if cached:
        exact = next(
            (row for row in cached if _normalize_text(row.get('title')) == _normalize_text(author_name)),
            cached[0],
        )
        cover_url = _large_author_cover_url(exact.get('cover_url') or '')
        payload.update({
            'title': exact.get('title') or author_name,
            'year': _safe_int(exact.get('year')),
            'cover_url': cover_url,
            'description': exact.get('description') or '',
        })
    return payload


def _large_author_cover_url(cover_url):
    if 'covers.openlibrary.org/a/olid/' not in (cover_url or ''):
        return cover_url or ''
    return re.sub(r'-[SML]\.jpg$', '-L.jpg', cover_url)


def _safe_external_lookup(fetcher, log_message, log_arg):
    try:
        return fetcher()
    except (RequestException, TimeoutError, OSError, ValueError):
        logger.warning(log_message, log_arg, exc_info=True)
        return []
    except BaseException as exc:
        logger.warning('External lookup aborted with %s', type(exc).__name__, exc_info=True)
        return []


def _get_or_create_author_node(user, tree, author_payload, index=0):
    title = (author_payload.get('title') or '').strip()[:255]
    title_norm = _normalize_text(title)
    for node in Node.objects.filter(user=user, tree=tree, node_type='author'):
        if _normalize_text(node.title) == title_norm:
            changed = []
            if author_payload.get('cover_url') and not node.cover_image:
                node.cover_image = author_payload['cover_url']
                changed.append('cover_image')
            if author_payload.get('description') and not node.description:
                node.description = author_payload['description'][:1000]
                changed.append('description')
            if author_payload.get('year') and not node.year:
                node.year = author_payload['year']
                changed.append('year')
            if changed:
                node.save(update_fields=changed)
            return node, False

    node = Node.objects.create(
        user=user,
        tree=tree,
        title=title or 'Unknown author',
        node_type='author',
        author='Author',
        year=author_payload.get('year'),
        description=(author_payload.get('description') or '')[:1000],
        cover_image=author_payload.get('cover_url') or '',
        pos_x=None,
        pos_y=None,
        style={
            'color': '#263f32',
            'glow': '#8ed18b',
            'border': '#9dcc7a',
        },
    )
    return node, True


def _get_or_create_tree_book_from_library(user, tree, book_payload, source_book, parent, index=0):
    existing = _find_existing_tree_book(user, book_payload, tree=tree)
    if existing:
        changed = []
        if existing.parent_id != parent.id:
            existing.parent = parent
            changed.append('parent')
        if existing.pos_x is not None or existing.pos_y is not None:
            existing.pos_x = None
            existing.pos_y = None
            changed.extend(['pos_x', 'pos_y'])
        for field, value in {
            'author': book_payload.get('author') or existing.author,
            'genre': book_payload.get('genre') or existing.genre,
            'year': book_payload.get('year') or existing.year,
            'isbn': book_payload.get('isbn') or existing.isbn,
            'cover_image': book_payload.get('cover_image') or existing.cover_image,
            'description': book_payload.get('description') or existing.description,
        }.items():
            if value and getattr(existing, field) != value:
                setattr(existing, field, value)
                changed.append(field)
        if changed:
            existing.save(update_fields=sorted(set(changed)))
        return existing, False

    node = Node.objects.create(
        user=user,
        tree=tree,
        node_type='book',
        title=(book_payload.get('title') or 'Untitled')[:255],
        author=(book_payload.get('author') or '')[:255],
        genre=(book_payload.get('genre') or '')[:100],
        series=(book_payload.get('series') or '')[:255],
        year=book_payload.get('year'),
        rating=book_payload.get('rating'),
        isbn=(book_payload.get('isbn') or '')[:20],
        cover_image=(book_payload.get('cover_image') or '')[:1000],
        description=book_payload.get('description') or '',
        parent=parent,
        shelf=getattr(source_book, 'shelf', book_payload.get('shelf') or Node.SHELF_WANT_TO_READ),
        custom_shelf=getattr(source_book, 'custom_shelf', book_payload.get('custom_shelf') or ''),
        date_read=getattr(source_book, 'date_read', book_payload.get('date_read')),
        notes=getattr(source_book, 'notes', book_payload.get('notes') or ''),
        style={
            'generated_by': 'auto_tree',
            'library_shadow': True,
        },
    )
    return node, True


def _get_user_book_recommendations(user, limit=8):
    cache_key = _cache_key(
        f'my-books:recommendations:v2:user:{user.id}:limit:{limit}',
        _library_state_token(user),
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    library_books = _get_library_books(user)
    existing_keys = {
        _book_key(book.title, book.author)
        for book in library_books
    }
    existing_isbns = {
        _normalize_goodreads_isbn(book.isbn)
        for book in library_books
        if _normalize_goodreads_isbn(book.isbn)
    }
    profile = _recommendation_profile(library_books)
    candidates = _recommendation_candidates(profile)

    scored = []
    seen = set()
    for candidate in candidates:
        key = _book_key(candidate.get('title'), candidate.get('author'))
        isbn = _normalize_goodreads_isbn(candidate.get('isbn'))
        if not key or key in seen or key in existing_keys or (isbn and isbn in existing_isbns):
            continue
        seen.add(key)
        score, reason = _score_recommendation(candidate, profile)
        if score <= 0:
            continue
        row = {
            'title': candidate.get('title') or '',
            'author': candidate.get('author') or 'Unknown author',
            'genre': candidate.get('genre') or '',
            'year': candidate.get('year') or '',
            'isbn': candidate.get('isbn') or '',
            'cover_url': candidate.get('cover_url') or candidate.get('cover_image') or '',
            'description': candidate.get('description') or '',
            'reason': reason,
            'score': score,
        }
        scored.append(row)

    scored.sort(key=lambda row: row['score'], reverse=True)
    results = scored[:limit]
    cache.set(cache_key, results, timeout=60 * 30)
    return results


def _library_state_token(user):
    identities = sorted(_library_book_identity(book) for book in _get_library_books(user))
    digest = hashlib.sha256('|'.join(identities).encode('utf-8')).hexdigest()[:16]
    return f'{len(identities)}:{digest}'


def _recommendation_profile(books):
    author_counts = Counter()
    genre_counts = Counter()
    keyword_counts = Counter()

    for book in books:
        shelf = getattr(book, 'shelf', '')
        weight = 3 if shelf in {Node.SHELF_READ, Node.SHELF_CURRENTLY_READING} else 1
        rating = getattr(book, 'rating', None)
        if rating and rating >= 4:
            weight += 2
        for author in _split_author_names(getattr(book, 'author', '')):
            author_counts[author] += weight
        genre = _genre_label(getattr(book, 'genre', ''))
        if genre:
            genre_counts[genre] += weight
        text = f"{getattr(book, 'title', '')} {getattr(book, 'notes', '')} {getattr(book, 'description', '')}"
        for token in _recommendation_keywords(text):
            keyword_counts[token] += 1

    return {
        'authors': author_counts,
        'genres': genre_counts,
        'keywords': keyword_counts,
    }


def _recommendation_keywords(text):
    stop_words = {
        'the', 'and', 'for', 'with', 'from', 'that', 'this', 'book', 'novel',
        'story', 'read', 'about', 'into', 'your', 'their', 'they', 'them',
    }
    tokens = _normalize_text(text).split()
    return [token for token in tokens if len(token) > 3 and token not in stop_words][:20]


def _recommendation_candidates(profile):
    candidates = []
    for book in _curated_landing_books():
        candidates.append(book)
    return candidates


def _score_recommendation(candidate, profile):
    author = candidate.get('author') or ''
    genre = _genre_label(candidate.get('genre') or '')
    title = candidate.get('title') or ''
    score = 1
    reasons = []

    for author_name in _split_author_names(author):
        author_weight = profile['authors'].get(author_name, 0)
        if not author_weight:
            author_weight = profile['authors'].get(_matching_counter_key(profile['authors'], author_name), 0)
        if author_weight:
            score += 8 + author_weight
            reasons.append(f'Because you read {author_name}')
            break

    genre_weight = profile['genres'].get(genre, 0)
    if genre and genre_weight:
        score += 5 + genre_weight
        reasons.append(f'More {genre}')

    title_tokens = set(_recommendation_keywords(title))
    keyword_hits = title_tokens.intersection(profile['keywords'])
    if keyword_hits:
        score += min(4, len(keyword_hits))
        if not reasons:
            reasons.append('Matches themes in your library')

    if candidate.get('cover_url') or candidate.get('cover_image'):
        score += 1

    return score, reasons[0] if reasons else 'Based on your reading shelf'


def _matching_counter_key(counter, value):
    value_norm = _normalize_text(value)
    for key in counter:
        if _normalize_text(key) == value_norm:
            return key
    return ''


def _create_tree_version(user, tree, label, reason='manual', comment=''):
    snapshot = _build_tree_snapshot(user, tree)
    return TreeVersion.objects.create(
        user=user,
        tree=tree,
        label=label,
        comment=comment,
        reason=reason,
        snapshot=snapshot,
    )


def _build_tree_snapshot(user, tree):
    nodes = Node.objects.filter(user=user, tree=tree).order_by('date_added')
    edges = Edge.objects.filter(user=user, tree=tree).order_by('id')
    return {
        'nodes': [
            {
                'id': str(node.id),
                'title': node.title,
                'node_type': node.node_type,
                'author': node.author,
                'genre': node.genre,
                'series': node.series,
                'year': node.year,
                'description': node.description,
                'rating': node.rating,
                'isbn': node.isbn,
                'cover_image': node.cover_image,
                'parent': str(node.parent_id) if node.parent_id else None,
                'pos_x': node.pos_x,
                'pos_y': node.pos_y,
                'style': node.style,
                'date_read': node.date_read.isoformat() if node.date_read else None,
                'shelf': node.shelf,
                'custom_shelf': node.custom_shelf,
                'badges': node.badges,
                'notes': node.notes,
            }
            for node in nodes
        ],
        'edges': [
            {
                'id': str(edge.id),
                'source': str(edge.source_id),
                'target': str(edge.target_id),
                'edge_type': edge.edge_type,
                'label': edge.label,
                'style': edge.style,
            }
            for edge in edges
        ],
    }


def _restore_tree_snapshot(user, tree, snapshot):
    from datetime import date

    node_rows = snapshot.get('nodes') or []
    edge_rows = snapshot.get('edges') or []

    Edge.objects.filter(user=user, tree=tree).delete()
    Node.objects.filter(user=user, tree=tree).delete()

    created_nodes = {}
    for row in node_rows:
        node_id = uuid.UUID(row['id'])
        node = Node.objects.create(
            id=node_id,
            user=user,
            tree=tree,
            title=row.get('title') or 'Untitled',
            node_type=row.get('node_type') or 'book',
            author=row.get('author') or '',
            genre=row.get('genre') or '',
            series=row.get('series') or '',
            year=row.get('year'),
            description=row.get('description') or '',
            rating=row.get('rating'),
            isbn=row.get('isbn') or '',
            cover_image=row.get('cover_image') or '',
            pos_x=row.get('pos_x'),
            pos_y=row.get('pos_y'),
            style=row.get('style') or {},
            date_read=date.fromisoformat(row['date_read']) if row.get('date_read') else None,
            shelf=row.get('shelf') or Node.SHELF_WANT_TO_READ,
            custom_shelf=row.get('custom_shelf') or '',
            badges=row.get('badges') or [],
            notes=row.get('notes') or '',
        )
        created_nodes[str(node_id)] = node

    for row in node_rows:
        parent_id = row.get('parent')
        node = created_nodes.get(row.get('id'))
        if node and parent_id and parent_id in created_nodes:
            node.parent = created_nodes[parent_id]
            node.save(update_fields=['parent'])

    for row in edge_rows:
        edge_id = str(row.get('id') or '')
        if edge_id.startswith('parent-'):
            continue
        source = created_nodes.get(row.get('source'))
        target = created_nodes.get(row.get('target'))
        if not source or not target:
            continue
        try:
            edge_uuid = uuid.UUID(edge_id)
        except (TypeError, ValueError):
            continue
        Edge.objects.create(
            id=edge_uuid,
            user=user,
            tree=tree,
            source=source,
            target=target,
            edge_type=row.get('edge_type') or 'custom',
            label=row.get('label') or '',
            style=row.get('style') or {},
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def goodreads_import_preview(request):
    upload = request.FILES.get('csv_file')
    if not upload:
        return Response({'detail': 'Please upload a Goodreads CSV file.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        raw_csv = upload.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        return Response({'detail': 'Could not read this CSV. Please export it from Goodreads as UTF-8 CSV.'}, status=status.HTTP_400_BAD_REQUEST)

    rows = _parse_goodreads_csv(raw_csv)
    if not rows:
        return Response({'detail': 'No Goodreads books were found in this file.'}, status=status.HTTP_400_BAD_REQUEST)

    books = [_annotate_import_book(request.user, row) for row in rows]
    return Response({
        'books': books,
        'total': len(books),
        'importable_count': sum(1 for book in books if not book['exists']),
        'existing_count': sum(1 for book in books if book['exists']),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def goodreads_import_confirm(request):
    requested_books = request.data.get('books') or []
    if not isinstance(requested_books, list):
        return Response({'detail': 'Books must be a list.'}, status=status.HTTP_400_BAD_REQUEST)

    created = []
    skipped = []
    with transaction.atomic():
        for raw_book in requested_books[:1000]:
            book = _clean_import_payload(raw_book)
            if not book.get('title'):
                continue

            existing = _find_existing_book(request.user, book)
            if existing:
                skipped.append({
                    'title': book['title'],
                    'author': book.get('author', ''),
                    'reason': 'Already in your tree',
                    'existing_id': str(existing.id),
                })
                continue

            imported_book = ImportedBook.objects.create(
                user=request.user,
                source=ImportedBook.SOURCE_GOODREADS,
                source_key=book.get('source_key', ''),
                title=book['title'],
                author=book.get('author', ''),
                year=book.get('year'),
                rating=book.get('rating'),
                isbn=book.get('isbn', ''),
                cover_image=book.get('cover_image', ''),
                shelf=book.get('shelf') or Node.SHELF_WANT_TO_READ,
                custom_shelf=book.get('custom_shelf', ''),
                date_read=book.get('date_read'),
                notes=book.get('notes', ''),
            )
            created.append(ImportedBookSerializer(imported_book).data)

    return Response({
        'created_count': len(created),
        'skipped_count': len(skipped),
        'created': created,
        'skipped': skipped,
    }, status=status.HTTP_201_CREATED)


def _parse_goodreads_csv(raw_csv):
    reader = csv.DictReader(io.StringIO(raw_csv))
    books = []
    for row in reader:
        book = _goodreads_row_to_book(row)
        if book.get('title'):
            books.append(book)
    return books[:1000]


def _goodreads_row_to_book(row):
    title = _csv_value(row, 'Title')
    author = _csv_value(row, 'Author') or _csv_value(row, 'Additional Authors')
    isbn = _normalize_goodreads_isbn(_csv_value(row, 'ISBN13') or _csv_value(row, 'ISBN'))
    year = _safe_int(_csv_value(row, 'Original Publication Year') or _csv_value(row, 'Year Published'))
    rating = _safe_float(_csv_value(row, 'My Rating'))
    exclusive_shelf = _csv_value(row, 'Exclusive Shelf').lower()
    shelves = _csv_value(row, 'Bookshelves')
    date_read = _parse_goodreads_date(_csv_value(row, 'Date Read'))
    review = _csv_value(row, 'My Review')

    return {
        'source_key': _csv_value(row, 'Book Id') or isbn,
        'title': title,
        'author': author,
        'isbn': isbn,
        'year': year,
        'rating': rating,
        'shelf': _goodreads_shelf(exclusive_shelf),
        'custom_shelf': _goodreads_custom_shelf(shelves),
        'date_read': date_read.isoformat() if date_read else None,
        'notes': review,
        'cover_image': _open_library_cover_url(isbn) if isbn else '',
    }


def _annotate_import_book(user, book):
    existing = _find_existing_book(user, book)
    return {
        **book,
        'exists': bool(existing),
        'match': 'Already in your tree' if existing else 'Ready to import',
        'existing_id': str(existing.id) if existing else '',
    }


def _clean_import_payload(raw_book):
    valid_shelves = {value for value, _ in Node.SHELF_CHOICES}
    shelf = raw_book.get('shelf') if raw_book.get('shelf') in valid_shelves else Node.SHELF_WANT_TO_READ
    return {
        'title': str(raw_book.get('title') or '').strip()[:255],
        'source_key': str(raw_book.get('source_key') or '').strip()[:160],
        'author': str(raw_book.get('author') or '').strip()[:255],
        'isbn': _normalize_goodreads_isbn(raw_book.get('isbn'))[:20],
        'year': _safe_int(raw_book.get('year')),
        'rating': _safe_float(raw_book.get('rating')),
        'shelf': shelf,
        'custom_shelf': str(raw_book.get('custom_shelf') or '').strip()[:80],
        'date_read': _parse_goodreads_date(raw_book.get('date_read')),
        'notes': str(raw_book.get('notes') or '').strip(),
        'cover_image': str(raw_book.get('cover_image') or '').strip()[:1000],
    }


def _find_existing_book(user, book):
    imported_existing = _find_existing_imported_book(user, book)
    if imported_existing:
        return imported_existing

    return _find_existing_tree_book(user, book)


def _find_existing_tree_book(user, book, tree=None):

    isbn = _normalize_goodreads_isbn(book.get('isbn'))
    if isbn:
        queryset = Node.objects.filter(user=user, node_type='book', isbn=isbn)
        if tree is not None:
            queryset = queryset.filter(tree=tree)
        existing = queryset.first()
        if existing:
            return existing

    title = _normalize_text(book.get('title'))
    author = _normalize_text(book.get('author'))
    if not title:
        return None

    candidates = Node.objects.filter(user=user, node_type='book', title__iexact=str(book.get('title') or '').strip())
    if tree is not None:
        candidates = candidates.filter(tree=tree)
    for candidate in candidates:
        if _normalize_text(candidate.title) == title and _normalize_text(candidate.author) == author:
            return candidate
    return None


def _find_existing_imported_book(user, book):
    source_key = str(book.get('source_key') or '').strip()
    if source_key:
        existing = ImportedBook.objects.filter(
            user=user,
            source=ImportedBook.SOURCE_GOODREADS,
            source_key=source_key,
        ).first()
        if existing:
            return existing

    isbn = _normalize_goodreads_isbn(book.get('isbn'))
    if isbn:
        existing = ImportedBook.objects.filter(user=user, isbn=isbn).first()
        if existing:
            return existing

    title = _normalize_text(book.get('title'))
    author = _normalize_text(book.get('author'))
    if not title:
        return None

    candidates = ImportedBook.objects.filter(user=user, title__iexact=str(book.get('title') or '').strip())
    for candidate in candidates:
        if _normalize_text(candidate.title) == title and _normalize_text(candidate.author) == author:
            return candidate
    return None


def _csv_value(row, key):
    return str(row.get(key) or '').strip()


def _normalize_goodreads_isbn(value):
    normalized = str(value or '').replace('=', '').replace('"', '').replace('-', '').strip()
    return ''.join(ch for ch in normalized if ch.isdigit() or ch.upper() == 'X')


def _safe_int(value):
    try:
        parsed = int(str(value or '').strip())
    except (TypeError, ValueError):
        return None
    return parsed if 0 < parsed < 3000 else None


def _safe_count(value):
    try:
        parsed = int(str(value or '').strip())
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _safe_float(value):
    try:
        parsed = float(str(value or '').strip())
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= 5 else None


def _parse_goodreads_date(value):
    from datetime import datetime

    raw = str(value or '').strip()
    if not raw:
        return None
    for fmt in ('%Y/%m/%d', '%Y-%m-%d', '%m/%d/%Y', '%b %d, %Y', '%B %d, %Y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _goodreads_shelf(exclusive_shelf):
    shelf_map = {
        'read': Node.SHELF_READ,
        'currently-reading': Node.SHELF_CURRENTLY_READING,
        'to-read': Node.SHELF_WANT_TO_READ,
    }
    return shelf_map.get(exclusive_shelf, Node.SHELF_WANT_TO_READ)


def _goodreads_custom_shelf(shelves):
    values = [
        value.strip()
        for value in str(shelves or '').split(',')
        if value.strip() and value.strip() not in {'read', 'currently-reading', 'to-read'}
    ]
    return values[0][:80] if values else ''


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

    cache_key = _cache_key('book-search:v4', query.lower())
    cached_results = cache.get(cache_key)
    if cached_results is not None:
        return Response({'results': cached_results})

    results = _search_books_combined(query)
    cache.set(cache_key, results, timeout=60 * 30)
    return Response({'results': results})


@api_view(['GET'])
def search_authors(request):
    """Autocomplete author nodes by author name."""
    query = (request.query_params.get('q') or '').strip()
    if len(query) < 2:
        return Response({'results': []})

    cache_key = _cache_key('author-search:v1', query.lower())
    cached_results = cache.get(cache_key)
    if cached_results is not None:
        return Response({'results': cached_results})

    try:
        results = _search_authors_open_library(query)
    except Exception:
        logger.exception('Open Library author lookup failed for query=%r', query)
        results = []
    cache.set(cache_key, results, timeout=60 * 60)
    return Response({'results': results})


@api_view(['GET'])
def critic_reviews(request):
    title = (request.query_params.get('title') or '').strip()
    author = (request.query_params.get('author') or '').strip()
    isbn = _normalize_goodreads_isbn(request.query_params.get('isbn'))
    if not title and not isbn:
        return Response({'results': [], 'detail': 'No book title or ISBN was provided.'})

    cache_value = isbn or f'{title}:{author}'
    cache_key = _cache_key('critic-reviews:nyt:v1', cache_value.lower())
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    if not getattr(settings, 'NYTIMES_BOOKS_API_KEY', ''):
        payload = {
            'results': [],
            'detail': 'No NYTimes critic reviews are configured yet.',
        }
        cache.set(cache_key, payload, timeout=60 * 30)
        return Response(payload)

    try:
        results = _search_nytimes_book_reviews(title=title, author=author, isbn=isbn)
    except Exception:
        logger.exception('NYTimes book review lookup failed for title=%r author=%r isbn=%r', title, author, isbn)
        results = []

    payload = {
        'results': results,
        'detail': '' if results else 'No New York Times critic review was found for this book.',
    }
    cache.set(cache_key, payload, timeout=60 * 60 * 24 * 14)
    return Response(payload)


def _cache_key(prefix, value):
    digest = hashlib.sha256(str(value or '').encode('utf-8')).hexdigest()[:24]
    return f'{prefix}:{digest}'


def _search_books_combined(query):
    isbn_query = _normalize_isbn_query(query)
    if isbn_query:
        try:
            isbn_results = _search_books_google_isbn(isbn_query)
            if isbn_results:
                return isbn_results
        except Exception:
            logger.exception('Google Books ISBN lookup failed for isbn=%r', isbn_query)

    with ThreadPoolExecutor(max_workers=2) as executor:
        google_future = executor.submit(_search_books_google, query)
        open_library_future = executor.submit(_search_books_open_library, query)

        try:
            google_results = google_future.result(timeout=4.5)
        except requests.HTTPError as exc:
            if getattr(exc.response, 'status_code', None) == 429:
                logger.warning('Google Books rate-limited query=%r; using Open Library fallback.', query)
            else:
                logger.exception('Google Books lookup failed for query=%r', query)
            google_results = []
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
            'edition_count': canonical.get('edition_count') or row.get('edition_count') or '',
            'ratings_count': (
                canonical.get('ratings_count')
                or row.get('ratings_count')
                or google_match.get('ratings_count')
                or ''
            ),
            'average_rating': (
                canonical.get('average_rating')
                or row.get('average_rating')
                or google_match.get('average_rating')
                or ''
            ),
            'reader_count': canonical.get('reader_count') or row.get('reader_count') or '',
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
    query_tokens = set(query_norm.split())
    title_tokens = set(title.split())
    author_tokens = set(author.split())
    score = 0
    if title == query_norm:
        score += 100
    elif title and title in query_norm:
        score += 80
    elif title.startswith(query_norm):
        score += 55
    elif query_norm in title:
        score += 25
    if title_tokens and title_tokens.issubset(query_tokens):
        score += 35
    if author_tokens and query_tokens and author_tokens.intersection(query_tokens):
        score += 28
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
    score += _safe_count(row.get('edition_count')) // 12
    score += min(_safe_count(row.get('ratings_count')) // 5, 18)
    score += min(_safe_count(row.get('reader_count')) // 20, 16)
    score += _known_book_rank_boost(row)
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


def _normalize_isbn_query(value):
    normalized = ''.join(ch for ch in str(value or '') if ch.isdigit() or ch.upper() == 'X')
    return normalized if len(normalized) in (10, 13) else ''


def _google_volume_to_row(item):
    info = item.get('volumeInfo', {})
    title = (info.get('title') or '').strip()
    if not title:
        return None

    authors = info.get('authors') or []
    categories = info.get('categories') or []
    published = info.get('publishedDate') or ''
    year = (published[:4] if published else '')
    desc = info.get('description') or ''
    ratings_count = _safe_count(info.get('ratingsCount'))

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

    return {
        'title': title,
        'author': author_text,
        'genre': _genre_label(categories[0] if categories else ''),
        'year': year,
        'isbn': isbn,
        'isbn_options': [isbn_13, isbn_10],
        'cover_url': cover_url,
        'description': desc,
        'ratings_count': ratings_count,
        'average_rating': info.get('averageRating') or '',
        '_score': has_cover * 4 + has_author * 2,
    }


def _search_books_google_isbn(isbn):
    resp = requests.get(
        'https://www.googleapis.com/books/v1/volumes',
        params=_google_books_params({'q': f'isbn:{isbn}', 'maxResults': 3, 'printType': 'books'}),
        headers={'User-Agent': 'Readwoods/1.0 (+https://localhost)'},
        timeout=3.5,
    )
    resp.raise_for_status()
    rows = [
        row for row in (_google_volume_to_row(item) for item in resp.json().get('items', []))
        if row
    ]
    for row in rows:
        row.pop('_score', None)
    return rows


def _apply_known_book_metadata(row):
    overrides = _known_book_overrides()
    author_key = _normalize_text((row.get('author') or '').split(',')[0])
    override = overrides.get((_normalize_text(row.get('title')), author_key))
    return {**row, **override} if override else row


def _known_book_rank_boost(row):
    author_key = _normalize_text((row.get('author') or '').split(',')[0])
    return 65 if (_normalize_text(row.get('title')), author_key) in _known_book_overrides() else 0


def _known_book_overrides():
    return {
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
        ('beloved', 'toni morrison'): {
            'isbn': '9781400033416',
            'year': '1987',
            'cover_url': _open_library_cover_url('9781400033416'),
            'genre': 'Fiction - Historical',
        },
        ('dune', 'frank herbert'): {
            'isbn': '9780441172719',
            'year': '1965',
            'cover_url': _open_library_cover_url('9780441172719'),
            'genre': 'Fiction - Science Fiction',
        },
        ('the hobbit', 'j r r tolkien'): {
            'isbn': '9780547928227',
            'year': '1937',
            'cover_url': _open_library_cover_url('9780547928227'),
            'genre': 'Fiction - Fantasy',
        },
        ('the hobbit', 'john ronald reuel tolkien'): {
            'isbn': '9780547928227',
            'year': '1937',
            'cover_url': _open_library_cover_url('9780547928227'),
            'genre': 'Fiction - Fantasy',
        },
        ('kindred', 'octavia e butler'): {
            'isbn': '9780807083697',
            'year': '1979',
            'cover_url': _open_library_cover_url('9780807083697'),
            'genre': 'Fiction - Science Fiction',
        },
        ('the tunnel', 'william h gass'): {
            'year': '1995',
            'genre': 'Fiction - Literary',
        },
        ('the tunnel', 'william gass'): {
            'year': '1995',
            'genre': 'Fiction - Literary',
        },
        ('the recognitions', 'william gaddis'): {
            'year': '1955',
            'genre': 'Fiction - Literary',
        },
        ('jr', 'william gaddis'): {
            'year': '1975',
            'genre': 'Fiction - Literary',
        },
        ('gravity s rainbow', 'thomas pynchon'): {
            'year': '1973',
            'genre': 'Fiction - Literary',
        },
        ('white noise', 'don delillo'): {
            'year': '1985',
            'genre': 'Fiction - Literary',
        },
    }


def _search_books_google(query, max_results=8):
    resp = requests.get(
        'https://www.googleapis.com/books/v1/volumes',
        params=_google_books_params({
            'q': f'intitle:{query}',
            'maxResults': max_results,
            'printType': 'books',
        }),
        headers={'User-Agent': 'Readwoods/1.0 (+https://localhost)'},
        timeout=3.5,
    )

    if resp.status_code == 429:
        raise requests.HTTPError('Google Books rate-limited request', response=resp)
    resp.raise_for_status()

    data = resp.json()
    items = data.get('items', [])

    results = [
        row for row in (_google_volume_to_row(item) for item in items)
        if row
    ]

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
        params={
            'q': query,
            'limit': max_results,
            'fields': (
                'title,author_name,subject,first_publish_year,isbn,cover_i,key,'
                'edition_count,ratings_average,ratings_count,want_to_read_count,'
                'currently_reading_count,already_read_count'
            ),
        },
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
        reader_count = (
            _safe_count(doc.get('want_to_read_count'))
            + _safe_count(doc.get('currently_reading_count'))
            + _safe_count(doc.get('already_read_count'))
        )

        results.append({
            'title': title,
            'author': author_text,
            'genre': _genre_label(subjects[0] if subjects else ''),
            'year': year,
            'isbn': isbn,
            'isbn_options': normalized_isbns,
            'cover_url': cover_url,
            'description': '',
            'edition_count': _safe_count(doc.get('edition_count')),
            'ratings_count': _safe_count(doc.get('ratings_count')),
            'average_rating': doc.get('ratings_average') or '',
            'reader_count': reader_count,
        })

    return results


def _search_authors_open_library(query, max_results=8, timeout=3.5):
    resp = requests.get(
        'https://openlibrary.org/search/authors.json',
        params={'q': query, 'limit': max_results},
        headers={'User-Agent': 'Readwoods/1.0 (+https://localhost)'},
        timeout=timeout,
    )
    resp.raise_for_status()
    docs = resp.json().get('docs') or []
    results = []
    query_norm = _normalize_text(query)
    for doc in docs:
        name = (doc.get('name') or '').strip()
        if not name:
            continue
        author_key = str(doc.get('key') or '').replace('/authors/', '').strip()
        birth_date = str(doc.get('birth_date') or '').strip()
        year_match = re.search(r'\b(\d{4})\b', birth_date)
        results.append({
            'title': name,
            'author': 'Author',
            'node_type': 'author',
            'genre': '',
            'year': year_match.group(1) if year_match else '',
            'isbn': '',
            'cover_url': f'https://covers.openlibrary.org/a/olid/{author_key}-M.jpg' if author_key else '',
            'description': doc.get('top_work') or '',
            '_score': 100 if _normalize_text(name) == query_norm else int(doc.get('work_count') or 0),
        })
    results.sort(key=lambda row: row.get('_score', 0), reverse=True)
    for row in results:
        row.pop('_score', None)
    return results[:max_results]


def _search_nytimes_book_reviews(title='', author='', isbn=''):
    searches = []
    if isbn:
        searches.append({'isbn': isbn})
    if title:
        title_params = {'title': title}
        if author:
            title_params['author'] = author
        searches.append(title_params)

    rows = []
    for search_params in searches:
        params = {
            'api-key': settings.NYTIMES_BOOKS_API_KEY,
            **search_params,
        }
        resp = requests.get(
            'https://api.nytimes.com/svc/books/v3/reviews.json',
            params=params,
            headers={'User-Agent': 'Readwoods/1.0 (+https://localhost)'},
            timeout=3.5,
        )
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        rows = resp.json().get('results') or []
        if rows:
            break

    results = []
    for row in rows[:5]:
        url = row.get('url') or ''
        if not url:
            continue
        results.append({
            'source': 'The New York Times',
            'book_title': row.get('book_title') or title,
            'book_author': row.get('book_author') or author,
            'review_title': row.get('headline') or row.get('summary') or 'NYTimes Review',
            'reviewer': row.get('byline') or '',
            'published_date': row.get('publication_dt') or '',
            'summary': row.get('summary') or '',
            'url': url,
        })
    return results


def _fetch_cover_google(title, author=''):
    try:
        q = f"intitle:{title}"
        if author:
            q += f"+inauthor:{author}"
        resp = requests.get(
            'https://www.googleapis.com/books/v1/volumes',
            params=_google_books_params({'q': q, 'maxResults': 1}),
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


def _google_books_params(params):
    params = dict(params)
    api_key = getattr(settings, 'GOOGLE_BOOKS_API_KEY', '')
    if api_key:
        params['key'] = api_key
    return params
