from rest_framework import serializers
from django.db.models import Q
from .models import Node, Edge, FriendRequest, Friendship, CommunityPost, ImportedBook, TreeVersion


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
            'shelf', 'custom_shelf',
            'badges', 'notes', 'children_count',
        ]

    def get_children_count(self, obj):
        if hasattr(obj, 'children_count'):
            return obj.children_count
        return obj.children.count()

    def get_cover_url(self, obj):
        request = self.context.get('request')
        url = obj.get_cover_url()
        if url and request and url.startswith('/'):
            return request.build_absolute_uri(url)
        return url

    def validate(self, attrs):
        """Protect tree integrity: disallow self-parent and cycles."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            parent = attrs.get('parent')
            if parent and parent.user_id != request.user.id:
                raise serializers.ValidationError({'parent': 'Parent must belong to the current user.'})

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


class ImportedBookSerializer(serializers.ModelSerializer):
    cover_url = serializers.SerializerMethodField()

    class Meta:
        model = ImportedBook
        fields = [
            'id', 'source', 'source_key', 'title', 'author', 'year', 'rating',
            'isbn', 'cover_image', 'cover_url', 'date_added', 'date_read',
            'shelf', 'custom_shelf', 'notes',
        ]

    def get_cover_url(self, obj):
        return obj.get_cover_url()


class TreeVersionSerializer(serializers.ModelSerializer):
    node_count = serializers.SerializerMethodField()
    edge_count = serializers.SerializerMethodField()

    class Meta:
        model = TreeVersion
        fields = ['id', 'label', 'reason', 'created_at', 'node_count', 'edge_count']

    def get_node_count(self, obj):
        return len((obj.snapshot or {}).get('nodes') or [])

    def get_edge_count(self, obj):
        return len((obj.snapshot or {}).get('edges') or [])


class TreeDataSerializer(serializers.Serializer):
    """Full tree payload for the frontend."""
    nodes = NodeSerializer(many=True)
    edges = EdgeSerializer(many=True)


class FriendRequestSerializer(serializers.ModelSerializer):
    from_username = serializers.CharField(source='from_user.username', read_only=True)
    to_username = serializers.CharField(source='to_user.username', read_only=True)

    class Meta:
        model = FriendRequest
        fields = [
            'id', 'from_user', 'to_user', 'from_username', 'to_username',
            'status', 'message', 'created_at', 'updated_at',
        ]
        read_only_fields = ['status', 'created_at', 'updated_at']

    def validate(self, attrs):
        request = self.context.get('request')
        from_user = attrs.get('from_user') or getattr(request, 'user', None)
        to_user = attrs.get('to_user')

        if from_user and to_user and from_user.id == to_user.id:
            raise serializers.ValidationError({'to_user': 'You cannot send a request to yourself.'})

        if from_user and to_user:
            existing_request = FriendRequest.objects.filter(
                from_user=from_user,
                to_user=to_user,
                status=FriendRequest.STATUS_PENDING,
            )
            if existing_request.exists():
                raise serializers.ValidationError({'detail': 'A pending request already exists.'})

            if Friendship.objects.filter(
                Q(user_a=from_user, user_b=to_user) | Q(user_a=to_user, user_b=from_user)
            ).exists():
                raise serializers.ValidationError({'detail': 'You are already connected.'})

        return attrs


class FriendshipSerializer(serializers.ModelSerializer):
    user_a_username = serializers.CharField(source='user_a.username', read_only=True)
    user_b_username = serializers.CharField(source='user_b.username', read_only=True)

    class Meta:
        model = Friendship
        fields = ['id', 'user_a', 'user_b', 'user_a_username', 'user_b_username', 'created_at']
        read_only_fields = ['created_at']


class CommunityPostSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = CommunityPost
        fields = [
            'id', 'user', 'username', 'title', 'content',
            'progress_status', 'visibility', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']
