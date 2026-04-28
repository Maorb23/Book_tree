import requests
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.cache import cache
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework import status

from .models import Node, Edge
from .serializers import NodeSerializer, EdgeSerializer


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Page views
# ──────────────────────────────────────────────

def landing(request):
    return render(request, 'landing.html', {
        'recommended_books': _get_landing_recommendations(),
    })


@login_required
def tree_page(request):
    return render(request, 'tree.html')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('tree:tree')

    form = UserCreationForm(request.POST or None)
    next_url = request.POST.get('next') or request.GET.get('next')
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect(next_url or 'tree:tree')

    return render(request, 'register.html', {
        'form': form,
        'next_url': next_url,
    })


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


# ──────────────────────────────────────────────
# Tree data – full snapshot
# ──────────────────────────────────────────────

@api_view(['GET'])
def tree_data(request):
    """Return all nodes + edges for the frontend to render."""
    nodes = Node.objects.all()
    edges = Edge.objects.select_related('source', 'target').all()

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

    return Response({'nodes': node_data, 'edges': edge_data})


# ──────────────────────────────────────────────
# Node CRUD
# ──────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticatedOrReadOnly])
def node_list(request):
    if request.method == 'GET':
        nodes = Node.objects.all()
        serializer = NodeSerializer(nodes, many=True, context={'request': request})
        return Response(serializer.data)

    serializer = NodeSerializer(data=request.data)
    if serializer.is_valid():
        node = serializer.save()
        # Auto-fetch cover if not supplied
        if not node.cover_image and node.isbn:
            node.cover_image = _fetch_cover_open_library(node.isbn)
            node.save(update_fields=['cover_image'])
        elif not node.cover_image and node.title:
            node.cover_image = _fetch_cover_google(node.title, node.author)
            node.save(update_fields=['cover_image'])
        return Response(NodeSerializer(node, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticatedOrReadOnly])
def node_detail(request, pk):
    node = get_object_or_404(Node, pk=pk)

    if request.method == 'GET':
        return Response(NodeSerializer(node, context={'request': request}).data)

    if request.method in ('PUT', 'PATCH'):
        serializer = NodeSerializer(node, data=request.data,
                                    partial=(request.method == 'PATCH'),
                                    context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    node.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticatedOrReadOnly])
def edge_list(request):
    if request.method == 'GET':
        edges = Edge.objects.all()
        serializer = EdgeSerializer(edges, many=True)
        return Response(serializer.data)

    serializer = EdgeSerializer(data=request.data)
    if serializer.is_valid():
        source = serializer.validated_data['source']
        target = serializer.validated_data['target']
        edge_type = serializer.validated_data.get('edge_type', 'custom')

        if source.id == target.id:
            return Response(
                {'detail': 'Source and target must be different nodes.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if Edge.objects.filter(source=source, target=target, edge_type=edge_type).exists():
            return Response(
                {'detail': 'This connection already exists.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        edge = serializer.save()
        return Response(EdgeSerializer(edge).data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticatedOrReadOnly])
def edge_detail(request, pk):
    edge = get_object_or_404(Edge, pk=pk)

    if request.method == 'PATCH':
        serializer = EdgeSerializer(edge, data=request.data, partial=True)
        if serializer.is_valid():
            saved = serializer.save()
            return Response(EdgeSerializer(saved).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    edge.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


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

    cache_key = f"book-search:{query.lower()}"
    cached_results = cache.get(cache_key)
    if cached_results is not None:
        return Response({'results': cached_results})

    try:
        google_results = _search_books_google(query)
        if google_results:
            cache.set(cache_key, google_results, timeout=60 * 10)
            return Response({'results': google_results})
    except Exception:
        logger.exception('Google Books lookup failed for query=%r', query)

    try:
        fallback_results = _search_books_open_library(query)
        cache.set(cache_key, fallback_results, timeout=60 * 10)
        return Response({'results': fallback_results})
    except Exception:
        logger.exception('Open Library lookup failed for query=%r', query)
        return Response({'results': []})


def _search_books_google(query, max_results=8):
    resp = requests.get(
        'https://www.googleapis.com/books/v1/volumes',
        params={
            'q': f'intitle:{query}',
            'maxResults': max_results,
            'printType': 'books',
        },
        headers={'User-Agent': 'Readwoods/1.0 (+https://localhost)'},
        timeout=6,
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
            'genre': categories[0] if categories else '',
            'year': year,
            'isbn': isbn,
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
        timeout=6,
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
        isbn = normalized_isbns[0] if normalized_isbns else ''

        cover_i = doc.get('cover_i')
        cover_url = f'https://covers.openlibrary.org/b/id/{cover_i}-L.jpg' if cover_i else ''

        results.append({
            'title': title,
            'author': author_text,
            'genre': subjects[0] if subjects else '',
            'year': year,
            'isbn': isbn,
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
            timeout=5,
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
    try:
        url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
        resp = requests.head(url, timeout=4)
        if resp.status_code == 200 and int(resp.headers.get('Content-Length', 1000)) > 1000:
            return url
    except Exception:
        pass
    return ''


def _open_library_cover_url(isbn):
    normalized = (isbn or '').replace('-', '').strip()
    if not normalized:
        return ''
    return f"https://covers.openlibrary.org/b/isbn/{normalized}-L.jpg"


def _get_landing_recommendations(limit=6):
    cache_key = f'landing:recommendations:v1:{limit}'
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

    picks = []
    seen_titles = set()

    db_nodes = (
        Node.objects
        .filter(node_type='book')
        .exclude(title='')
        .order_by('-rating', '-date_added')[:30]
    )

    for node in db_nodes:
        title_key = node.title.strip().lower()
        if not title_key or title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        db_cover = node.get_cover_url() or ''
        if not db_cover and node.isbn:
            db_cover = _open_library_cover_url(node.isbn)
        if not db_cover and node.title:
            db_cover = _fetch_cover_google(node.title, node.author or '')
        picks.append({
            'title': node.title,
            'genre': (node.genre or 'Community pick')[:60],
            'author': (node.author or '').strip(),
            'cover_url': db_cover,
        })
        if len(picks) >= limit:
            break

    if len(picks) < limit:
        query_plan = [
            'best fantasy books',
            'best science fiction books',
            'popular mystery books',
        ]
        for query in query_plan:
            try:
                results = _search_books_google(query, max_results=8)
            except Exception:
                results = []

            for row in results:
                title = (row.get('title') or '').strip()
                title_key = title.lower()
                if not title or title_key in seen_titles:
                    continue
                seen_titles.add(title_key)
                picks.append({
                    'title': title,
                    'genre': (row.get('genre') or 'Recommended')[:60],
                    'author': (row.get('author') or '').strip(),
                    'cover_url': row.get('cover_url') or _open_library_cover_url(row.get('isbn') or ''),
                })
                if len(picks) >= limit:
                    break
            if len(picks) >= limit:
                break

    if len(picks) < limit:
        curated = [
            {
                'title': 'Project Hail Mary',
                'genre': 'Science Fiction',
                'author': 'Andy Weir',
                'cover_url': _open_library_cover_url('9780593135204'),
            },
            {
                'title': 'The Way of Kings',
                'genre': 'Fantasy',
                'author': 'Brandon Sanderson',
                'cover_url': _open_library_cover_url('9780765326355'),
            },
            {
                'title': 'The Thursday Murder Club',
                'genre': 'Mystery',
                'author': 'Richard Osman',
                'cover_url': _open_library_cover_url('9781984880963'),
            },
            {
                'title': 'East of Eden',
                'genre': 'Classics',
                'author': 'John Steinbeck',
                'cover_url': _open_library_cover_url('9780140186390'),
            },
            {
                'title': 'Sapiens',
                'genre': 'History',
                'author': 'Yuval Noah Harari',
                'cover_url': _open_library_cover_url('9780062316097'),
            },
            {
                'title': 'Tomorrow, and Tomorrow, and Tomorrow',
                'genre': 'Literary Fiction',
                'author': 'Gabrielle Zevin',
                'cover_url': _open_library_cover_url('9780593321201'),
            },
        ]

        for row in curated:
            title_key = row['title'].strip().lower()
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            picks.append(row)
            if len(picks) >= limit:
                break

    for idx, book in enumerate(picks):
        book['tone'] = tone_classes[idx % len(tone_classes)]

    final_picks = picks[:limit]
    cache.set(cache_key, final_picks, timeout=60 * 10)
    return final_picks