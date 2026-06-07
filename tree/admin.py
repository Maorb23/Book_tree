from django.contrib import admin
from .models import (
    Node, Edge, UserProfile, FriendRequest, Friendship, CommunityPost,
    ReadingChallenge, DailyPageLog, BookReview,
)


@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ('title', 'node_type', 'author', 'genre', 'date_added')
    list_filter = ('node_type', 'genre')
    search_fields = ('title', 'author', 'genre')
    readonly_fields = ('id', 'date_added')


@admin.register(Edge)
class EdgeAdmin(admin.ModelAdmin):
    list_display = ('source', 'target', 'edge_type')
    list_filter = ('edge_type',)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_name', 'created_at')
    search_fields = ('user__username', 'display_name')


@admin.register(FriendRequest)
class FriendRequestAdmin(admin.ModelAdmin):
    list_display = ('from_user', 'to_user', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('from_user__username', 'to_user__username')


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ('user_a', 'user_b', 'created_at')
    search_fields = ('user_a__username', 'user_b__username')


@admin.register(CommunityPost)
class CommunityPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'visibility', 'created_at')
    list_filter = ('visibility', 'progress_status')
    search_fields = ('title', 'user__username')


@admin.register(BookReview)
class BookReviewAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'rating', 'updated_at')
    search_fields = ('title', 'author', 'user__username', 'review')


@admin.register(ReadingChallenge)
class ReadingChallengeAdmin(admin.ModelAdmin):
    list_display = ('user', 'year', 'target_books', 'updated_at')
    list_filter = ('year',)
    search_fields = ('user__username',)


@admin.register(DailyPageLog)
class DailyPageLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'book_title', 'pages', 'log_date', 'created_at')
    list_filter = ('log_date',)
    search_fields = ('user__username', 'book_title', 'book_author')
