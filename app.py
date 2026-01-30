"""
Flask application factory for Shiny Handouts.

Provides Flask + HTMX frontend with:
- File upload with progress
- Task cards with polling updates
- Nested file browser (Date → Lecture → Artifacts)
- SSE progress endpoint
"""

import os
from datetime import datetime, timezone

from flask import Flask
from flask_login import LoginManager

from models import User, db, init_db

login_manager = LoginManager()


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="templates/flask")

    # Configuration
    app.config["SECRET_KEY"] = os.environ.get(
        "SECRET_KEY", "dev-secret-key-change-in-production"
    )
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2GB max upload

    # Data directories
    app.config["UPLOAD_FOLDER"] = os.path.join("data", "input")
    app.config["OUTPUT_FOLDER"] = os.path.join("data", "output")

    # Ensure directories exist
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["OUTPUT_FOLDER"], exist_ok=True)

    # Initialize database
    init_db(app)

    # Initialize login manager
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id: str) -> User:
        return db.session.get(User, int(user_id))

    # Register blueprints
    from routes import api_bp, auth_bp, main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/auth")

    # Template context processors
    @app.context_processor
    def utility_processor():
        return {
            "now": datetime.now(timezone.utc),
        }

    return app


def create_celery_app(app: Flask = None):
    """Create Celery app with Flask application context."""
    from celery_app import celery_app

    if app is None:
        app = create_app()

    class ContextTask(celery_app.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app.Task = ContextTask
    return celery_app


# Application entry point
app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
