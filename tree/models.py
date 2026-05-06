from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Q
import uuid


class Node(models.Model):
    NODE_TYPES = [
        ("book", "Book"),
        ("author", "Author"),
        ("genre", "Genre"),
        ("series", "Series"),
        ("custom", "Custom"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='nodes')
    title = models.CharField(max_length=255)
    node_type = models.CharField(max_length=20, choices=NODE_TYPES, default="book")

    author = models.CharField(max_length=255, blank=True)
    genre = models.CharField(max_length=100, blank=True)
    series = models.CharField(max_length=255, blank=True)
    year = models.IntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    rating = models.FloatField(null=True, blank=True)
    isbn = models.CharField(max_length=20, blank=True)

    cover_image = models.URLField(max_length=1000, blank=True)
    cover_upload = models.ImageField(upload_to='covers/', null=True, blank=True)

    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )

    # Position on the canvas (optional manual override)
    pos_x = models.FloatField(null=True, blank=True)
    pos_y = models.FloatField(null=True, blank=True)

    # Visual customization
    style = models.JSONField(default=dict, blank=True)

    date_added = models.DateTimeField(auto_now_add=True)
    date_read = models.DateField(null=True, blank=True)

    badges = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['date_added']
        indexes = [
            models.Index(fields=['user', 'date_added']),
        ]

    def __str__(self):
        return f"{self.title} ({self.node_type})"

    def get_cover_url(self):
        """Return best available cover image URL."""
        if self.cover_upload:
            return self.cover_upload.url
        if self.cover_image:
            return self.cover_image
        return None


class Edge(models.Model):
    """Explicit relationship between two nodes."""
    EDGE_TYPES = [
        ("progression", "Reading Progression"),
        ("genre", "Same Genre"),
        ("author", "Same Author"),
        ("series", "Same Series"),
        ("custom", "Custom"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='edges')
    source = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="edges_from")
    target = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="edges_to")
    edge_type = models.CharField(max_length=20, choices=EDGE_TYPES, default="progression")
    label = models.CharField(max_length=100, blank=True)
    style = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ('user', 'source', 'target', 'edge_type')
        indexes = [
            models.Index(fields=['user', 'edge_type']),
        ]

    def __str__(self):
        return f"{self.source.title} → {self.target.title} ({self.edge_type})"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True)
    avatar_url = models.URLField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.display_name or self.user.username


class FriendRequest(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    from_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='friend_requests_sent',
    )
    to_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='friend_requests_received',
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    message = models.CharField(max_length=280, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['to_user', 'status']),
            models.Index(fields=['from_user', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['from_user', 'to_user'],
                condition=Q(status='pending'),
                name='unique_pending_friend_request',
            ),
        ]

    def clean(self):
        if self.from_user_id == self.to_user_id:
            raise ValidationError({'to_user': 'You cannot send a request to yourself.'})

        if self.status == self.STATUS_PENDING and self.from_user_id and self.to_user_id:
            duplicate_exists = FriendRequest.objects.filter(
                from_user=self.from_user,
                to_user=self.to_user,
                status=self.STATUS_PENDING,
            ).exclude(pk=self.pk).exists()
            if duplicate_exists:
                raise ValidationError({'to_user': 'A pending request already exists.'})

    def __str__(self):
        return f"{self.from_user} → {self.to_user} ({self.status})"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Friendship(models.Model):
    user_a = models.ForeignKey(User, on_delete=models.CASCADE, related_name='friendships_a')
    user_b = models.ForeignKey(User, on_delete=models.CASCADE, related_name='friendships_b')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user_a', 'user_b'], name='unique_friendship_pair'),
        ]

    def clean(self):
        if self.user_a_id == self.user_b_id:
            raise ValidationError({'user_b': 'You cannot connect with yourself.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.user_a_id and self.user_b_id and self.user_a_id > self.user_b_id:
            self.user_a, self.user_b = self.user_b, self.user_a
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user_a} → {self.user_b}"


class CommunityPost(models.Model):
    VISIBILITY_PUBLIC = 'public'
    VISIBILITY_FRIENDS = 'friends'
    VISIBILITY_PRIVATE = 'private'
    VISIBILITY_CHOICES = [
        (VISIBILITY_PUBLIC, 'Public'),
        (VISIBILITY_FRIENDS, 'Friends'),
        (VISIBILITY_PRIVATE, 'Private'),
    ]

    STATUS_PLANNING = 'planning'
    STATUS_READING = 'reading'
    STATUS_FINISHED = 'finished'
    STATUS_CHOICES = [
        (STATUS_PLANNING, 'Planning'),
        (STATUS_READING, 'Reading'),
        (STATUS_FINISHED, 'Finished'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='community_posts')
    title = models.CharField(max_length=160)
    content = models.TextField()
    progress_status = models.CharField(max_length=12, choices=STATUS_CHOICES, blank=True)
    visibility = models.CharField(max_length=12, choices=VISIBILITY_CHOICES, default=VISIBILITY_PUBLIC)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} → {self.user.username}"
