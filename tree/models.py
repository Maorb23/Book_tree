from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Q
import uuid


class Tree(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trees')
    name = models.CharField(max_length=160)
    description = models.CharField(max_length=280, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', 'name']
        indexes = [
            models.Index(fields=['user', 'is_default'], name='tree_user_default_idx'),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.name}"


class Node(models.Model):
    SHELF_ALL = "all"
    SHELF_WANT_TO_READ = "want_to_read"
    SHELF_CURRENTLY_READING = "currently_reading"
    SHELF_READ = "read"
    SHELF_DID_NOT_FINISH = "did_not_finish"
    SHELF_CHOICES = [
        (SHELF_ALL, "All"),
        (SHELF_WANT_TO_READ, "Want to Read"),
        (SHELF_CURRENTLY_READING, "Currently Reading"),
        (SHELF_READ, "Read"),
        (SHELF_DID_NOT_FINISH, "Did Not Finish"),
    ]

    NODE_TYPES = [
        ("book", "Book"),
        ("author", "Author"),
        ("genre", "Genre"),
        ("series", "Series"),
        ("custom", "Custom"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='nodes')
    tree = models.ForeignKey(Tree, null=True, blank=True, on_delete=models.CASCADE, related_name='nodes')
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
    shelf = models.CharField(max_length=32, choices=SHELF_CHOICES, default=SHELF_WANT_TO_READ)
    custom_shelf = models.CharField(max_length=80, blank=True)

    badges = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['date_added']
        indexes = [
            models.Index(fields=['user', 'date_added'], name='tree_node_user_date_idx'),
            models.Index(fields=['tree', 'date_added'], name='tree_node_tree_date_idx'),
        ]

    def __str__(self):
        return f"{self.title} ({self.node_type})"

    def save(self, *args, **kwargs):
        if self.user_id and not self.tree_id:
            tree = Tree.objects.filter(user_id=self.user_id, is_default=True).first()
            if tree is None:
                tree = Tree.objects.create(user_id=self.user_id, name='Main Tree', is_default=True)
            self.tree = tree
        return super().save(*args, **kwargs)

    def get_cover_url(self):
        """Return best available cover image URL."""
        if self.cover_upload:
            return self.cover_upload.url
        if self.cover_image:
            return self.cover_image
        return None

    @property
    def library_source(self):
        return "tree"


class ImportedBook(models.Model):
    SOURCE_GOODREADS = "goodreads"
    SOURCE_SEARCH = "search"
    SOURCE_CHOICES = [
        (SOURCE_GOODREADS, "Goodreads"),
        (SOURCE_SEARCH, "Search"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='imported_books')
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES, default=SOURCE_GOODREADS)
    source_key = models.CharField(max_length=160, blank=True)
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255, blank=True)
    year = models.IntegerField(null=True, blank=True)
    rating = models.FloatField(null=True, blank=True)
    isbn = models.CharField(max_length=20, blank=True)
    cover_image = models.URLField(max_length=1000, blank=True)
    date_added = models.DateTimeField(auto_now_add=True)
    date_read = models.DateField(null=True, blank=True)
    shelf = models.CharField(max_length=32, choices=Node.SHELF_CHOICES, default=Node.SHELF_WANT_TO_READ)
    custom_shelf = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['date_added']
        indexes = [
            models.Index(fields=['user', 'source', 'date_added'], name='import_book_user_src_idx'),
            models.Index(fields=['user', 'isbn'], name='import_book_user_isbn_idx'),
        ]

    def __str__(self):
        return f"{self.title} ({self.source})"

    def get_cover_url(self):
        return self.cover_image or None

    @property
    def library_source(self):
        return "imported"


class TreeVersion(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tree_versions')
    tree = models.ForeignKey(Tree, null=True, blank=True, on_delete=models.CASCADE, related_name='versions')
    label = models.CharField(max_length=180)
    comment = models.TextField(blank=True)
    reason = models.CharField(max_length=80, blank=True)
    snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at'], name='tree_version_user_date_idx'),
            models.Index(fields=['tree', 'created_at'], name='tree_version_tree_date_idx'),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.label}"


class ReadingChallenge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reading_challenges')
    year = models.PositiveIntegerField(default=2026)
    target_books = models.PositiveIntegerField(default=25)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'year')
        indexes = [
            models.Index(fields=['user', 'year'], name='read_chal_user_year_idx'),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.year} reading challenge"


class DailyPageLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='daily_page_logs')
    node = models.ForeignKey(Node, null=True, blank=True, on_delete=models.CASCADE, related_name='page_logs')
    imported_book = models.ForeignKey(ImportedBook, null=True, blank=True, on_delete=models.CASCADE, related_name='page_logs')
    book_title = models.CharField(max_length=255)
    book_author = models.CharField(max_length=255, blank=True)
    log_date = models.DateField()
    pages = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-log_date', '-created_at']
        indexes = [
            models.Index(fields=['user', 'log_date'], name='page_log_user_date_idx'),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.pages} pages on {self.log_date}"


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
    tree = models.ForeignKey(Tree, null=True, blank=True, on_delete=models.CASCADE, related_name='edges')
    source = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="edges_from")
    target = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="edges_to")
    edge_type = models.CharField(max_length=20, choices=EDGE_TYPES, default="progression")
    label = models.CharField(max_length=100, blank=True)
    style = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ('user', 'tree', 'source', 'target', 'edge_type')
        indexes = [
            models.Index(fields=['user', 'edge_type'], name='tree_edge_user_type_idx'),
            models.Index(fields=['tree', 'edge_type'], name='tree_edge_tree_type_idx'),
        ]

    def __str__(self):
        return f"{self.source.title} → {self.target.title} ({self.edge_type})"


    def save(self, *args, **kwargs):
        if not self.tree_id and self.source_id:
            self.tree = self.source.tree
        return super().save(*args, **kwargs)


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
