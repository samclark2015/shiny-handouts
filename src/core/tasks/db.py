"""
Database operations for jobs and artifacts.
"""

import logging
import os

from asgiref.sync import sync_to_async

from core.storage import get_storage, is_s3_enabled


async def create_artifact(job_id: int, artifact_type, file_path: str) -> None:
    """Create an artifact record immediately when a file is generated.

    Args:
        job_id: The job ID
        artifact_type: Type of artifact (PDF_HANDOUT, EXCEL_STUDY_TABLE, PDF_VIGNETTE, etc.)
        file_path: Path to the generated file (local path or S3 key)
        source_id: Deprecated, kept for backwards compatibility (ignored)
    """

    if not file_path:
        return

    # For S3, file_path is the S3 key; for local, check if file exists
    if not is_s3_enabled() and not os.path.exists(file_path):
        return

    try:
        # Get file size (works for both local and S3)
        storage = get_storage()
        try:
            file_size = await storage.get_file_size(file_path)
        except Exception:
            file_size = 0

        # Get the filename from the path
        file_name = os.path.basename(file_path)

        await _create_artifact_sync(job_id, artifact_type, file_path, file_name, file_size)
    except Exception as e:
        logging.exception(f"Failed to create artifact for job {job_id}: {e}")


@sync_to_async
def _create_artifact_sync(
    job_id: int,
    artifact_type,
    file_path: str,
    file_name: str,
    file_size: int,
) -> None:
    """Synchronous helper for creating artifacts."""
    from core.models import Artifact, Job

    job = Job.objects.get(id=job_id)

    # Check if artifact already exists for this job and file path
    existing = Artifact.objects.filter(job=job, file_path=file_path).first()

    if existing:
        # Update existing artifact
        existing.artifact_type = artifact_type
        existing.file_name = file_name
        existing.file_size = file_size
        existing.save()
    else:
        # Create new artifact
        Artifact.objects.create(
            job=job,
            artifact_type=artifact_type,
            file_path=file_path,
            file_name=file_name,
            file_size=file_size,
        )


@sync_to_async
def update_job_source_info(
    job_id: int, source_id: str, title: str | None = None, video_path: str | None = None
) -> None:
    """Update job with source information.

    Args:
        job_id: The job ID
        source_id: The source identifier
        title: Optional title (defaults to job label if not provided)
        video_path: Optional path to the video file
    """
    from core.models import Job

    job = Job.objects.get(id=job_id)

    job.source_id = source_id
    if title:
        job.title = title
    if video_path:
        job.video_path = video_path

    job.save(update_fields=["source_id", "title", "video_path"])
