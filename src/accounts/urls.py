"""URL patterns for accounts app."""

from django.urls import path

from . import views

app_name = "auth"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("callback/", views.oauth_callback, name="callback"),
    path("settings/", views.settings_view, name="settings"),
]
