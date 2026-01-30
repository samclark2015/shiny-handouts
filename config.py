"""
Configuration settings for Shiny Handouts.

Loads configuration from environment variables with sensible defaults.
"""

import os
from typing import Optional


class Config:
    """Base configuration."""

    # Flask
    SECRET_KEY: str = os.environ.get(
        "SECRET_KEY", "dev-secret-key-change-in-production"
    )
    DEBUG: bool = False
    TESTING: bool = False

    # Database
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL", "sqlite:///data/shiny_handouts.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    # Redis
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    REDIS_CACHE_URL: str = os.environ.get("REDIS_CACHE_URL", "redis://localhost:6379/1")

    # OAuth
    OAUTH_URL: Optional[str] = os.environ.get("OAUTH_URL")
    OAUTH_CLIENT_ID: Optional[str] = os.environ.get("OAUTH_CLIENT_ID")
    OAUTH_CLIENT_SECRET: Optional[str] = os.environ.get("OAUTH_CLIENT_SECRET")

    # OpenAI
    OPENAI_API_KEY: Optional[str] = os.environ.get("OPENAI_API_KEY")

    # File uploads
    MAX_CONTENT_LENGTH: int = 2 * 1024 * 1024 * 1024  # 2GB
    UPLOAD_FOLDER: str = os.path.join("data", "input")
    OUTPUT_FOLDER: str = os.path.join("data", "output")

    @classmethod
    def get_database_url(cls) -> str:
        """Get database URL with PostgreSQL URL fix."""
        url = cls.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    DATABASE_URL = "sqlite:///:memory:"


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False

    @classmethod
    def init_app(cls, app):
        """Production-specific initialization."""
        # Log to stderr in production
        import logging
        from logging import StreamHandler

        handler = StreamHandler()
        handler.setLevel(logging.INFO)
        app.logger.addHandler(handler)


# Configuration dictionary
config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config(config_name: Optional[str] = None):
    """Get configuration class by name."""
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")
    return config.get(config_name, config["default"])
