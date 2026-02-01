"""
Database operations for lectures and artifacts.
"""

import logging
import os
from datetime import UTC, datetime

from asgiref.sync import sync_to_async

from core.storage import upload_bytes, upload_file


@sync_to_async
def get_or_create_lecture(job_id: int, source_id: str | None = None):
    """Get or create lecture for a job, keyed by source_id.

    Args:
        job_id: The job ID
        source_id: Optional source ID. If not provided, will try to get from job's lecture.
    """
    from core.models import Job, Lecture

    job = Job.objects.select_related("user").get(id=job_id)

    # If source_id not provided, try to get from existing lecture
    if not source_id:
        try:
            existing_lecture = Lecture.objects.get(job=job)
            source_id = existing_lecture.source_id
        except Lecture.DoesNotExist:
            # No source_id and no existing lecture, create with empty source_id
            source_id = ""

    # Check if lecture already exists for this source_id and user
    if source_id:
        try:
            lecture = Lecture.objects.get(source_id=source_id, user=job.user)
            # Update the job reference if this is a retry
            if lecture.job_id != job.pk:
                lecture.job_id = job.pk
                lecture.save(update_fields=["job"])
            return lecture
        except Lecture.DoesNotExist:
            pass

    # Check if lecture exists by job (for backwards compatibility)
    try:
        lecture = Lecture.objects.get(job=job)
        # Update source_id if we have one now
        if source_id and not lecture.source_id:
            lecture.source_id = source_id
            lecture.save(update_fields=["source_id"])
        return lecture
    except Lecture.DoesNotExist:
        pass

    # Create new lecture
    lecture = Lecture(
        user=job.user,
        job=job,
        title=job.label,
        source_id=source_id,
        date=datetime.now(UTC),
    )
    lecture.save()
    return lecture


async def create_artifact(
    job_id: int,
    artifact_type,
    filename: str,
    content: str | bytes | None = None,
    local_path: str | None = None,
    content_type: str | None = None,
    source_id: str | None = None,
) -> str:
    """Upload content to storage and create an artifact record.

    This function handles both uploading content to storage and creating the
    corresponding database record.

    Args:
        job_id: The job ID
        artifact_type: Type of artifact (PDF_HANDOUT, EXCEL_STUDY_TABLE, etc.)
        filename: The output filename
        content: String or bytes content to upload (mutually exclusive with local_path)
        local_path: Path to a local file to upload (mutually exclusive with content)
        content_type: Optional MIME type for the content
        source_id: Optional source ID for lecture lookup

    Returns:
        The storage path (S3 key or local path)

    Raises:
        ValueError: If neither content nor local_path is provided
    """
    if content is None and local_path is None:
        raise ValueError("Either content or local_path must be provided")

    # Upload to storage
    if local_path is not None:
        storage_path = await upload_file(local_path, "output", filename)
        file_size = os.path.getsize(local_path)
    elif isinstance(content, str):
        content_bytes = content.encode("utf-8")
        storage_path = await upload_bytes(
            content_bytes, "output", filename, content_type=content_type
        )
        file_size = len(content_bytes)
    elif isinstance(content, bytes):
        storage_path = await upload_bytes(content, "output", filename, content_type=content_type)
        file_size = len(content)
    else:
        raise ValueError("content must be str or bytes")

    try:
        await _create_artifact_sync(
            job_id, artifact_type, storage_path, filename, file_size, source_id
        )
    except Exception as e:
        logging.exception(f"Failed to create artifact for job {job_id}: {e}")

    return storage_path


@sync_to_async
def _create_artifact_sync(
    job_id: int,
    artifact_type,
    file_path: str,
    file_name: str,
    file_size: int,
    source_id: str | None,
) -> None:
    """Synchronous helper for creating artifacts."""
    from core.models import Artifact, Job, Lecture

    job = Job.objects.select_related("user").get(id=job_id)

    # If source_id not provided, try to get from existing lecture
    if not source_id:
        try:
            existing_lecture = Lecture.objects.get(job=job)
            source_id = existing_lecture.source_id
        except Lecture.DoesNotExist:
            source_id = ""

    # Check if lecture already exists for this source_id and user
    lecture = None
    if source_id:
        try:
            lecture = Lecture.objects.get(source_id=source_id, user=job.user)
            if lecture.job != job.pk:
                lecture.job = job
                lecture.save(update_fields=["job"])
        except Lecture.DoesNotExist:
            pass

    # Check if lecture exists by job (for backwards compatibility)
    if not lecture:
        try:
            lecture = Lecture.objects.get(job=job)
            if source_id and not lecture.source_id:
                lecture.source_id = source_id
                lecture.save(update_fields=["source_id"])
        except Lecture.DoesNotExist:
            pass

    # Create new lecture if needed
    if not lecture:
        lecture = Lecture.objects.create(
            user=job.user,
            job=job,
            title=job.label,
            source_id=source_id,
            date=datetime.now(UTC),
        )

    # Check if artifact already exists for this lecture and file path
    existing = Artifact.objects.filter(lecture=lecture, file_path=file_path).first()

    if existing:
        # Update existing artifact
        existing.artifact_type = artifact_type
        existing.file_name = file_name
        existing.file_size = file_size
        existing.save()
    else:
        # Create new artifact
        Artifact.objects.create(
            lecture=lecture,
            artifact_type=artifact_type,
            file_path=file_path,
            file_name=file_name,
            file_size=file_size,
        )
