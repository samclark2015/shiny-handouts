"""
Flask-Migrate configuration for database migrations.
"""

from flask_migrate import Migrate

from app import create_app
from models import db

app = create_app()
migrate = Migrate(app, db)

if __name__ == "__main__":
    # This allows running: python migrations.py db init/migrate/upgrade
    import click
    from flask.cli import FlaskGroup

    @click.group(cls=FlaskGroup, create_app=lambda: app)
    def cli():
        """Management commands for Shiny Handouts."""
        pass

    cli()
