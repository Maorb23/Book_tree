from django.db import models
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
    source = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="edges_from")
    target = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="edges_to")
    edge_type = models.CharField(max_length=20, choices=EDGE_TYPES, default="progression")
    label = models.CharField(max_length=100, blank=True)
    style = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ('source', 'target', 'edge_type')

    def __str__(self):
        return f"{self.source.title} → {self.target.title} ({self.edge_type})"
