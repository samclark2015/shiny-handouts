"""
Database operations for lectures and artifacts.
"""

import logging
import os
from datetime import UTC, datetime

from asgiref.sync import sync_to_async


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


@sync_to_async
def create_artifact(
    job_id: int, artifact_type, file_path: str, source_id: str | None = None
) -> None:
    """Create an artifact record immediately when a file is generated.

    Args:
        job_id: The job ID
        artifact_type: Type of artifact (PDF_HANDOUT, EXCEL_STUDY_TABLE, PDF_VIGNETTE)
        file_path: Path to the generated file
        source_id: Optional source ID for lecture lookup
    """
    from core.models import Artifact

    if not file_path or not os.path.exists(file_path):
        return

    try:
        # Call the sync version directly since we're in sync context
        from core.models import Job, Lecture

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

        # Check if artifact already exists for this lecture and type
        existing = Artifact.objects.filter(lecture=lecture, artifact_type=artifact_type).first()

        if existing:
            # Update existing artifact
            existing.file_path = file_path
            existing.file_name = os.path.basename(file_path)
            existing.file_size = os.path.getsize(file_path)
            existing.save()
        else:
            # Create new artifact
            Artifact.objects.create(
                lecture=lecture,
                artifact_type=artifact_type,
                file_path=file_path,
                file_name=os.path.basename(file_path),
                file_size=int(os.path.getsize(file_path)),
            )
    except Exception as e:
        # Log error but don't fail the task
        logging.exception(f"Failed to create artifact for job {job_id}: {e}")
