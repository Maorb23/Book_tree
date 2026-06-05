from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls), # Admin site, this url is for site administrators to manage the application
    path('', include('tree.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
