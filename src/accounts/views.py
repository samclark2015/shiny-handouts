"""Views for accounts app - authentication, OAuth, and settings."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from pipeline.helpers import read_prompt

from .forms import SettingProfileForm
from .models import DEFAULT_SPREADSHEET_COLUMNS, SettingProfile


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


@login_required
def profiles_view(request):
    """Display list of user's setting profiles."""
    profiles = SettingProfile.objects.filter(user=request.user)

    return render(
        request,
        "accounts/profiles.html",
        {
            "profiles": profiles,
        },
    )


@login_required
def profile_create(request):
    """Create a new setting profile."""
    default_vignette = read_prompt("generate_vignette_questions")
    default_spreadsheet = read_prompt("generate_spreadsheet")
    default_mindmap = read_prompt("generate_mindmap")

    if request.method == "POST":
        form = SettingProfileForm(request.POST)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user

            # Store None if value equals the default
            vp = form.cleaned_data.get("vignette_prompt")
            sp = form.cleaned_data.get("spreadsheet_prompt")
            mp = form.cleaned_data.get("mindmap_prompt")

            if vp is not None and vp == default_vignette:
                profile.vignette_prompt = None
            if sp is not None and sp == default_spreadsheet:
                profile.spreadsheet_prompt = None
            if mp is not None and mp == default_mindmap:
                profile.mindmap_prompt = None

            profile.save()
            messages.success(request, f"Profile '{profile.name}' created successfully.")
            return redirect("auth:profiles")
    else:
        # Pre-populate with default prompt values
        initial = {
            "vignette_prompt": default_vignette,
            "spreadsheet_prompt": default_spreadsheet,
            "mindmap_prompt": default_mindmap,
        }
        form = SettingProfileForm(initial=initial)

    return render(
        request,
        "accounts/profile_form.html",
        {
            "form": form,
            "default_vignette": default_vignette,
            "default_spreadsheet": default_spreadsheet,
            "default_mindmap": default_mindmap,
            "columns": DEFAULT_SPREADSHEET_COLUMNS,
            "default_columns": DEFAULT_SPREADSHEET_COLUMNS,
            "is_edit": False,
        },
    )


@login_required
def profile_edit(request, profile_id: int):
    """Edit an existing setting profile."""
    profile = get_object_or_404(SettingProfile, id=profile_id, user=request.user)

    default_vignette = read_prompt("generate_vignette_questions")
    default_spreadsheet = read_prompt("generate_spreadsheet")
    default_mindmap = read_prompt("generate_mindmap")

    if request.method == "POST":
        form = SettingProfileForm(request.POST, instance=profile)
        if form.is_valid():
            # Store None if value equals the default
            vp = form.cleaned_data.get("vignette_prompt")
            sp = form.cleaned_data.get("spreadsheet_prompt")
            mp = form.cleaned_data.get("mindmap_prompt")

            if vp is not None and vp == default_vignette:
                form.instance.vignette_prompt = None
            if sp is not None and sp == default_spreadsheet:
                form.instance.spreadsheet_prompt = None
            if mp is not None and mp == default_mindmap:
                form.instance.mindmap_prompt = None

            form.save()
            messages.success(request, f"Profile '{profile.name}' updated successfully.")
            return redirect("auth:profiles")
    else:
        # Pre-populate with custom or default prompt values
        initial = {
            "vignette_prompt": profile.vignette_prompt or default_vignette,
            "spreadsheet_prompt": profile.spreadsheet_prompt or default_spreadsheet,
            "mindmap_prompt": profile.mindmap_prompt or default_mindmap,
        }
        form = SettingProfileForm(instance=profile, initial=initial)

    return render(
        request,
        "accounts/profile_form.html",
        {
            "form": form,
            "default_vignette": default_vignette,
            "default_spreadsheet": default_spreadsheet,
            "default_mindmap": default_mindmap,
            "columns": profile.get_spreadsheet_columns(),
            "default_columns": DEFAULT_SPREADSHEET_COLUMNS,
            "is_edit": True,
            "profile": profile,
        },
    )


@require_http_methods(["DELETE"])
@login_required
def profile_delete(request, profile_id: int):
    """Delete a setting profile."""
    profile = get_object_or_404(SettingProfile, id=profile_id, user=request.user)
    profile_name = profile.name
    profile.delete()

    return JsonResponse({"success": True, "message": f"Profile '{profile_name}' deleted."})
