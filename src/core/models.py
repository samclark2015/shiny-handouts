"""
Database models for Handout Generator core functionality.

Provides Job and Artifact models for pipeline processing.
"""


from django.conf import settings
from django.db import models
from django.utils import timezone


class JobStatus(models.TextChoices):
    """Enum for job status tracking."""

    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLING = "cancelling", "Cancelling"
    CANCELLED = "cancelled", "Cancelled"


class ArtifactType(models.TextChoices):
    """Types of artifacts that can be generated."""

    PDF_HANDOUT = "pdf_handout", "PDF Handout"
    EXCEL_STUDY_TABLE = "excel_study_table", "Excel Study Table"
    PDF_VIGNETTE = "pdf_vignette", "PDF Vignette"
    MERMAID_MINDMAP = "mermaid_mindmap", "Mermaid Mindmap"


class Job(models.Model):
    """Job model for tracking pipeline tasks."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    taskiq_task_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    # Job metadata
    label = models.CharField(max_length=255)
    title = models.CharField(max_length=255, blank=True, null=True)
    source_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    video_path = models.CharField(max_length=512, blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=JobStatus.choices,
        default=JobStatus.PENDING,
    )
    progress = models.FloatField(default=0.0)
    current_stage = models.CharField(max_length=255, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)

    # Input configuration (stored as JSON-compatible string)
    input_type = models.CharField(max_length=50)  # 'url', 'upload', 'panopto'
    input_data = models.TextField()  # JSON serialized input

    # Per-job output settings
    enable_excel = models.BooleanField(
        default=True,
        help_text="Generate Excel study table for this job",
    )
    enable_vignette = models.BooleanField(
        default=True,
        help_text="Generate vignette quiz questions for this job",
    )
    enable_mindmap = models.BooleanField(
        default=True,
        help_text="Generate mindmap diagram for this job",
    )

    # Setting profile reference (optional)
    setting_profile = models.ForeignKey(
        "accounts.SettingProfile",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="jobs",
        help_text="Settings profile used for this job",
    )

    # Timing
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "jobs"
        ordering = ["-created_at"]
        verbose_name = "job"
        verbose_name_plural = "jobs"

    def __str__(self):
        return f"Job {self.pk} - {self.label} ({self.status})"

    @property
    def duration(self) -> float | None:
        """Calculate job duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def is_active(self) -> bool:
        """Check if job is currently active."""
        return self.status in (JobStatus.PENDING, JobStatus.RUNNING)

    @property
    def is_terminal(self) -> bool:
        """Check if job has reached a terminal state."""
        return self.status in (
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        )

    @property
    def progress_percent(self) -> int:
        """Return progress as a percentage (0-100)."""
        return int(self.progress * 100)


class Artifact(models.Model):
    """Artifact model for generated files."""

    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name="artifacts",
    )

    # Artifact metadata
    artifact_type = models.CharField(max_length=30, choices=ArtifactType.choices)
    file_path = models.CharField(max_length=512)
    file_name = models.CharField(max_length=255)
    file_size = models.IntegerField(blank=True, null=True)

    # Timing
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "artifacts"
        ordering = ["-created_at"]
        verbose_name = "artifact"
        verbose_name_plural = "artifacts"

    def __str__(self):
        return f"{self.file_name} ({self.get_artifact_type_display()})"

    def get_download_path(self) -> str:
        """Get the relative path for downloading this artifact.

        For local storage, returns the filename.
        For S3, returns the S3 key stored in file_path.
        """
        return self.file_path if self.file_path else self.file_name

    def get_download_url(self) -> str:
        """Get the URL for downloading this artifact."""
        from django.urls import reverse

        return reverse("serve_file", kwargs={"filename": self.file_name})
