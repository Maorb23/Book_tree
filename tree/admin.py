from django.contrib import admin
from .models import Node, Edge


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
