import requests
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import Node, Edge
from .serializers import NodeSerializer, EdgeSerializer


# ──────────────────────────────────────────────
# Page views
# ──────────────────────────────────────────────

def landing(request):
    return render(request, 'landing.html')


def tree_page(request):
    return render(request, 'tree.html')


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

    try:
        resp = requests.get(
            'https://www.googleapis.com/books/v1/volumes',
            params={
                'q': f'intitle:{query}',
                'maxResults': 8,
                'printType': 'books',
            },
            timeout=6,
        )
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
                t = ident.get('type')
                v = (ident.get('identifier') or '').replace('-', '').strip()
                if t == 'ISBN_13' and not isbn_13:
                    isbn_13 = v
                elif t == 'ISBN_10' and not isbn_10:
                    isbn_10 = v
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

        return Response({'results': cleaned})
    except Exception:
        return Response({'results': []})


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
