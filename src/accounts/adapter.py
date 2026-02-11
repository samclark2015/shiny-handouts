"""
Custom allauth adapter for Authentik OAuth integration.

Maps OAuth user info to our custom User model.
"""

from allauth.account.utils import user_field
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class AuthentikSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Custom adapter for Authentik OAuth."""

    def populate_user(self, request, sociallogin, data):
        """
        Populate user fields from OAuth data.

        Authentik provides:
        - sub: unique user ID (oauth_id)
        - email: user's email
        - name: display name
        - preferred_username: username
        """
        user = super().populate_user(request, sociallogin, data)

        # Set name from OAuth data
        name = (
            data.get("name") or data.get("preferred_username") or data.get("email", "")
        )
        user_field(user, "name", name)

        return user

    def save_user(self, request, sociallogin, form=None):
        """Save user and update OAuth ID."""
        user = super().save_user(request, sociallogin, form)

        # Store the OAuth ID from the provider
        extra_data = sociallogin.account.extra_data
        oauth_id = extra_data.get("sub", "")

        if oauth_id and user.oauth_id != oauth_id:
            user.oauth_id = oauth_id
            user.save(update_fields=["oauth_id"])

        return user

    def pre_social_login(self, request, sociallogin):
        """
        Handle pre-login processing.

        If a user with this email exists but doesn't have an oauth_id,
        connect the social account to the existing user.
        """
        from accounts.models import User

        email = sociallogin.account.extra_data.get("email")
        oauth_id = sociallogin.account.extra_data.get("sub")

        if not email:
            return

        # Try to find existing user by OAuth ID first
        try:
            existing_user = User.objects.get(oauth_id=oauth_id)
            sociallogin.connect(request, existing_user)
            return
        except User.DoesNotExist:
            pass

        # Try to find by email
        try:
            existing_user = User.objects.get(email=email)
            # Update the OAuth ID
            if not existing_user.oauth_id:
                existing_user.oauth_id = oauth_id
                existing_user.save(update_fields=["oauth_id"])
            sociallogin.connect(request, existing_user)
        except User.DoesNotExist:
            pass

    def authentication_error(
        self, request, provider_id, error=None, exception=None, extra_context=None
    ):
        """Handle authentication errors gracefully."""
        from django.contrib import messages

        error_msg = (
            str(exception) if exception else str(error) if error else "Unknown error"
        )
        messages.error(request, f"Authentication failed: {error_msg}")
