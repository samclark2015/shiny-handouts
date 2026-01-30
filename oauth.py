"""
Flask-Dance OAuth integration for Authentik.

Provides OAuth authentication flow using Flask-Dance and Flask-Login.
"""

import os
from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, url_for
from flask_dance.consumer import OAuth2ConsumerBlueprint, oauth_authorized
from flask_dance.consumer.storage.sqla import SQLAlchemyStorage
from flask_login import current_user, login_user

from models import User, db


def create_authentik_blueprint() -> OAuth2ConsumerBlueprint:
    """Create the Authentik OAuth blueprint."""
    oauth_url = os.environ.get("OAUTH_URL", "")
    client_id = os.environ.get("OAUTH_CLIENT_ID", "")
    client_secret = os.environ.get("OAUTH_CLIENT_SECRET", "")

    # Parse OAuth discovery URL to get endpoints
    # Authentik uses OpenID Connect discovery
    base_url = oauth_url.rstrip("/").replace("/.well-known/openid-configuration", "")

    authentik_bp = OAuth2ConsumerBlueprint(
        "authentik",
        __name__,
        client_id=client_id,
        client_secret=client_secret,
        base_url=base_url,
        authorization_url=f"{base_url}/authorize/",
        token_url=f"{base_url}/token/",
        token_url_params={"include_client_id": True},
        scope=["openid", "email", "profile"],
    )

    return authentik_bp


def init_oauth(app):
    """Initialize OAuth with the Flask app."""
    authentik_bp = create_authentik_blueprint()

    @oauth_authorized.connect_via(authentik_bp)
    def authentik_logged_in(blueprint, token):
        """Handle successful OAuth login."""
        if not token:
            flash("Failed to log in.", category="error")
            return False

        # Get user info from the token
        resp = blueprint.session.get("/userinfo")
        if not resp.ok:
            flash("Failed to fetch user info.", category="error")
            return False

        user_info = resp.json()
        oauth_id = user_info.get("sub")
        email = user_info.get("email")
        name = user_info.get("name") or user_info.get("preferred_username") or email

        if not oauth_id or not email:
            flash("Invalid user information received.", category="error")
            return False

        # Find or create user
        user = User.query.filter_by(oauth_id=oauth_id).first()
        if not user:
            user = User.query.filter_by(email=email).first()
            if user:
                # Update existing user with OAuth ID
                user.oauth_id = oauth_id
            else:
                # Create new user
                user = User(
                    oauth_id=oauth_id,
                    email=email,
                    name=name,
                )
                db.session.add(user)

        # Update last login
        user.name = name
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()

        # Log in the user
        login_user(user)

        # Don't store the token in the database by returning False
        return False

    app.register_blueprint(authentik_bp, url_prefix="/auth")

    return authentik_bp


# Alternative: Simple OAuth routes if Flask-Dance setup is complex

oauth_simple_bp = Blueprint("oauth_simple", __name__)


@oauth_simple_bp.route("/oauth/login")
def oauth_login():
    """Redirect to OAuth provider."""
    from authlib.integrations.flask_client import OAuth

    oauth = OAuth()
    oauth_url = os.environ.get("OAUTH_URL", "")
    client_id = os.environ.get("OAUTH_CLIENT_ID", "")
    client_secret = os.environ.get("OAUTH_CLIENT_SECRET", "")

    oauth.register(
        "authentik",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=oauth_url,
        client_kwargs={"scope": "openid email profile"},
    )

    redirect_uri = url_for("oauth_simple.oauth_callback", _external=True)
    return oauth.authentik.authorize_redirect(redirect_uri)


@oauth_simple_bp.route("/oauth/callback")
def oauth_callback():
    """Handle OAuth callback."""
    from authlib.integrations.flask_client import OAuth

    oauth = OAuth()
    oauth_url = os.environ.get("OAUTH_URL", "")
    client_id = os.environ.get("OAUTH_CLIENT_ID", "")
    client_secret = os.environ.get("OAUTH_CLIENT_SECRET", "")

    oauth.register(
        "authentik",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=oauth_url,
        client_kwargs={"scope": "openid email profile"},
    )

    try:
        token = oauth.authentik.authorize_access_token()
    except Exception as e:
        flash(f"OAuth error: {e}", category="error")
        return redirect(url_for("auth.login"))

    user_info = token.get("userinfo", {})
    oauth_id = user_info.get("sub")
    email = user_info.get("email")
    name = user_info.get("name") or user_info.get("preferred_username") or email

    if not oauth_id or not email:
        flash("Invalid user information received.", category="error")
        return redirect(url_for("auth.login"))

    # Find or create user
    user = User.query.filter_by(oauth_id=oauth_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()
        if user:
            user.oauth_id = oauth_id
        else:
            user = User(
                oauth_id=oauth_id,
                email=email,
                name=name,
            )
            db.session.add(user)

    user.name = name
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    login_user(user)

    return redirect(url_for("main.index"))
