"""
Progress tracking and job status utilities.
"""

import json
from datetime import UTC, datetime

import redis.asyncio as aioredis

from .config import REDIS_URL, STAGE_START_PROGRESS, STAGE_WEIGHTS


class JobCancelledException(Exception):
    """Raised when a job has been cancelled."""

    pass


def calculate_overall_progress(stage_name: str, stage_progress: float) -> float:
    """Calculate overall pipeline progress from stage name and stage-specific progress.

    Args:
        stage_name: Name of the current stage (e.g., 'download_video')
        stage_progress: Progress within this stage (0.0 to 1.0)

    Returns:
        Overall progress from 0.0 to 1.0
    """
    if stage_name not in STAGE_WEIGHTS:
        return 0.0

    start = STAGE_START_PROGRESS[stage_name]
    weight = STAGE_WEIGHTS[stage_name]
    return start + (stage_progress * weight)


async def check_job_cancelled(job_id: int) -> bool:
    """Check if a job has been cancelled or is being cancelled."""
    from core.models import Job, JobStatus

    try:
        job = await Job.objects.aget(id=job_id)
        return job.status in (JobStatus.CANCELLING, JobStatus.CANCELLED)
    except Job.DoesNotExist:
        return True  # Treat missing job as cancelled


async def publish_progress(job_id: int, stage: str, progress: float, message: str = "") -> None:
    """Publish progress update to Redis pub/sub."""
    redis = await aioredis.from_url(REDIS_URL)
    try:
        await redis.publish(
            f"job:{job_id}:progress",
            json.dumps(
                {
                    "stage": stage,
                    "progress": progress,
                    "message": message,
                    "status": "running",
                }
            ),
        )
    finally:
        await redis.close()


async def update_job_progress(job_id: int, stage: str, progress: float, message: str) -> None:
    """Update job progress in the database and publish to Redis.

    Also checks for cancellation and raises JobCancelledException if cancelled.

    Args:
        job_id: The job ID to update
        stage: The current stage name (e.g., 'download_video')
        progress: Progress within the current stage (0.0 to 1.0)
        message: Human-readable progress message
    """
    from core.models import Job, JobStatus

    # Calculate overall progress across all stages
    overall_progress = calculate_overall_progress(stage, progress)

    try:
        job = await Job.objects.aget(id=job_id)

        # Check for cancellation
        if job.status == JobStatus.CANCELLING:
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.now(UTC)
            await job.asave(update_fields=["status", "completed_at"])

            raise JobCancelledException(f"Job {job_id} was cancelled")

        job.current_stage = message
        job.progress = overall_progress
        if job.status == JobStatus.PENDING:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(UTC)
        await job.asave(update_fields=["current_stage", "progress", "status", "started_at"])
    except Job.DoesNotExist:
        raise JobCancelledException(f"Job {job_id} no longer exists") from None

    await publish_progress(job_id, stage, overall_progress, message)


async def update_job_label(job_id: int, label: str) -> None:
    """Update job label in the database."""
    from core.models import Job

    try:
        job = await Job.objects.aget(id=job_id)
        job.label = label
        await job.asave(update_fields=["label"])
    except Job.DoesNotExist:
        pass


async def mark_job_completed(job_id: int, outputs: dict) -> None:
    """Mark a job as completed in the database."""
    from core.models import Job, JobStatus

    try:
        job = await Job.objects.select_related("user").aget(id=job_id)
        job.status = JobStatus.COMPLETED
        job.progress = 1.0
        job.completed_at = datetime.now(UTC)

        # Update source_id on job if provided
        if "source_id" in outputs:
            job.source_id = outputs["source_id"]
            await job.asave(update_fields=["status", "progress", "completed_at", "source_id"])
        else:
            await job.asave(update_fields=["status", "progress", "completed_at"])

        # Publish completion
        await publish_progress(job_id, "completed", 1.0, "Job completed successfully")

    except Job.DoesNotExist:
        pass
