"""
Database models for Shiny Handouts.

Supports hierarchical organization: Date → Lecture → Artifacts
Configurable DB backend via DATABASE_URL environment variable.
"""

import enum
import os
from datetime import datetime, timezone
from typing import Optional

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


db = SQLAlchemy(model_class=Base)


class JobStatus(enum.Enum):
    """Enum for job status tracking."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class User(UserMixin, db.Model):
    """User model for authentication."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    oauth_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    jobs: Mapped[list["Job"]] = relationship(
        "Job", back_populates="user", cascade="all, delete-orphan"
    )
    lectures: Mapped[list["Lecture"]] = relationship(
        "Lecture", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"

    def get_id(self) -> str:
        """Return the user ID as a string for Flask-Login."""
        return str(self.id)


class Job(db.Model):
    """Job model for tracking pipeline tasks."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )

    # Job metadata
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.PENDING, nullable=False
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    current_stage: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Input configuration (stored as JSON-compatible string)
    input_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'url', 'upload', 'panopto'
    input_data: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # JSON serialized input

    # Timing
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="jobs")
    lecture: Mapped[Optional["Lecture"]] = relationship(
        "Lecture", back_populates="job", uselist=False
    )

    def __repr__(self) -> str:
        return f"<Job {self.id} - {self.label} ({self.status.value})>"

    @property
    def duration(self) -> Optional[float]:
        """Calculate job duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class Lecture(db.Model):
    """Lecture model representing a processed video."""

    __tablename__ = "lectures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    job_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("jobs.id"), nullable=True
    )

    # Lecture metadata
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Processing metadata
    video_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="lectures")
    job: Mapped[Optional["Job"]] = relationship("Job", back_populates="lecture")
    artifacts: Mapped[list["Artifact"]] = relationship(
        "Artifact", back_populates="lecture", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Lecture {self.title}>"


class ArtifactType(enum.Enum):
    """Types of artifacts that can be generated."""

    PDF_HANDOUT = "pdf_handout"
    EXCEL_STUDY_TABLE = "excel_study_table"
    PDF_VIGNETTE = "pdf_vignette"


class Artifact(db.Model):
    """Artifact model for generated files."""

    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lecture_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lectures.id"), nullable=False
    )

    # Artifact metadata
    artifact_type: Mapped[ArtifactType] = mapped_column(
        Enum(ArtifactType), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timing
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    lecture: Mapped["Lecture"] = relationship("Lecture", back_populates="artifacts")

    def __repr__(self) -> str:
        return f"<Artifact {self.file_name} ({self.artifact_type.value})>"


def get_database_url() -> str:
    """Get database URL from environment, defaulting to SQLite for development."""
    return os.environ.get("DATABASE_URL", "sqlite:///shiny_handouts.db")


def init_db(app):
    """Initialize the database with the Flask app."""
    database_url = get_database_url()

    # Handle PostgreSQL URL format from some providers
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    with app.app_context():
        db.create_all()
