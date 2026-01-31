"""URL patterns for accounts app."""

from django.urls import path

from . import views

app_name = "auth"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("callback/", views.oauth_callback, name="callback"),
    path("settings/", views.settings_view, name="settings"),
    path("profiles/", views.profiles_view, name="profiles"),
    path("profiles/create/", views.profile_create, name="profile_create"),
    path("profiles/<int:profile_id>/edit/", views.profile_edit, name="profile_edit"),
    path("profiles/<int:profile_id>/delete/", views.profile_delete, name="profile_delete"),
]
