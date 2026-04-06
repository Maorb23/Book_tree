from rest_framework import serializers
from .models import Node, Edge


class NodeSerializer(serializers.ModelSerializer):
    children_count = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()

    class Meta:
        model = Node
        fields = [
            'id', 'title', 'node_type', 'author', 'genre', 'series',
            'year', 'description', 'rating', 'isbn',
            'cover_image', 'cover_url',
            'parent', 'pos_x', 'pos_y',
            'style', 'date_added', 'date_read',
            'badges', 'notes', 'children_count',
        ]

    def get_children_count(self, obj):
        return obj.children.count()

    def get_cover_url(self, obj):
        request = self.context.get('request')
        url = obj.get_cover_url()
        if url and request and url.startswith('/'):
            return request.build_absolute_uri(url)
        return url

    def validate(self, attrs):
        """Protect tree integrity: disallow self-parent and cycles."""
        parent = attrs.get('parent', serializers.empty)
        if parent is serializers.empty:
            return attrs

        instance = getattr(self, 'instance', None)
        if instance is None:
            return attrs

        if parent is None:
            return attrs

        if parent.id == instance.id:
            raise serializers.ValidationError({'parent': 'A node cannot be its own parent.'})

        cursor = parent
        while cursor is not None:
            if cursor.id == instance.id:
                raise serializers.ValidationError({'parent': 'This move creates a cycle in the tree.'})
            cursor = cursor.parent

        return attrs


class EdgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Edge
        fields = ['id', 'source', 'target', 'edge_type', 'label', 'style']


class TreeDataSerializer(serializers.Serializer):
    """Full tree payload for the frontend."""
    nodes = NodeSerializer(many=True)
    edges = EdgeSerializer(many=True)
