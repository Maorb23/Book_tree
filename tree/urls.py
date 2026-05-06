from django.urls import path
from . import views

app_name = 'tree'

urlpatterns = [
    # Pages
    path('', views.landing, name='landing'),
    path('community/', views.community_feed, name='community-feed'),
    path('community/my-posts/', views.community_my_posts, name='community-my-posts'),
    path('community/new/', views.community_create_post, name='community-create-post'),
    path('community/people/', views.community_people, name='community-people'),
    path('community/requests/', views.community_requests, name='community-requests'),
    path('community/friends/', views.community_friends, name='community-friends'),
    path('community/request/send/<int:user_id>/', views.send_friend_request, name='community-send-request'),
    path('community/request/<int:request_id>/accept/', views.accept_friend_request, name='community-accept-request'),
    path('community/request/<int:request_id>/reject/', views.reject_friend_request, name='community-reject-request'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('tree/', views.tree_page, name='tree'),
    path('book/', views.book_page, name='book'),

    # API
    path('api/tree/', views.tree_data, name='api-tree'),
    path('api/nodes/', views.node_list, name='api-node-list'),
    path('api/nodes/<str:pk>/', views.node_detail, name='api-node-detail'),
    path('api/edges/', views.edge_list, name='api-edge-list'),
    path('api/edges/<str:pk>/', views.edge_detail, name='api-edge-detail'),
    path('api/cover/', views.fetch_cover, name='api-cover'),
    path('api/book-search/', views.search_books, name='api-book-search'),
]
