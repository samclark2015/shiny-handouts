"""Views for accounts app - authentication and OAuth."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST


@require_GET
def login_view(request):
    """Display login page."""
    if request.user.is_authenticated:
        return redirect("main:index")
    return render(request, "accounts/login.html")


@require_GET
def logout_view(request):
    """Log out the user and redirect to login page."""
    logout(request)
    return redirect("auth:login")


@require_GET
def oauth_callback(request):
    """
    Handle OAuth callback from Authentik.

    This is a fallback handler - django-allauth should handle most OAuth flows.
    """
    # django-allauth handles the OAuth callback automatically
    # This view is for any custom post-auth processing if needed
    if request.user.is_authenticated:
        # Update last login time
        request.user.last_login = timezone.now()
        request.user.save(update_fields=["last_login"])
        return redirect("main:index")

    messages.error(request, "Authentication failed. Please try again.")
    return redirect("auth:login")
