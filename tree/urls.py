from django.urls import path
from . import views

app_name = 'tree'

urlpatterns = [
    # Pages
    path('', views.landing, name='landing'),
    path('tree/', views.tree_page, name='tree'),

    # API
    path('api/tree/', views.tree_data, name='api-tree'),
    path('api/nodes/', views.node_list, name='api-node-list'),
    path('api/nodes/<str:pk>/', views.node_detail, name='api-node-detail'),
    path('api/edges/', views.edge_list, name='api-edge-list'),
    path('api/edges/<str:pk>/', views.edge_detail, name='api-edge-detail'),
    path('api/cover/', views.fetch_cover, name='api-cover'),
    path('api/book-search/', views.search_books, name='api-book-search'),
]
