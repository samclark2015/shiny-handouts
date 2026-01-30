"""
URL configuration for Handout Generator project.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("auth/", include("accounts.urls")),
    path("auth/", include("allauth.urls")),  # allauth URLs without namespace
    path("api/", include("core.urls.api")),
    path("", include("core.urls.main")),
]
