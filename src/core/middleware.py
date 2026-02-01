"""
Custom Taskiq middleware for pipeline error handling.

Catches task failures and updates Job status in database.
"""

import logging
from typing import Any

from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

logger = logging.getLogger(__name__)


class PipelineErrorMiddleware(TaskiqMiddleware):
    """
    Middleware to handle pipeline task failures.

    When a task fails, this middleware:
    1. Extracts the job_id from task arguments
    2. Updates the Job record with FAILED status and error message
    3. Publishes failure notification to Redis pub/sub
    """

    async def post_execute(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],
    ) -> None:
        """Handle post-execution, checking for errors."""
        if not result.is_err:
            return

        from core.tasks import JobCancelledException

        if isinstance(result.error, JobCancelledException):
            # Job was cancelled, no need to mark as failed
            logger.info(
                f"Pipeline task {message.task_name} for job {self._extract_job_id(message)} was cancelled."
            )
            return

        # Extract job_id from task arguments
        job_id = self._extract_job_id(message)
        if not job_id:
            logger.warning(f"Task {message.task_name} failed but no job_id found in args")
            return

        error_message = self._format_error(result.error)

        logger.error(f"Pipeline task {message.task_name} failed for job {job_id}: {error_message}")

        # Update job status in database
        await self._mark_job_failed(job_id, error_message)

        # Publish failure to Redis pub/sub
        await self._publish_failure(job_id, error_message)

    def _extract_job_id(self, message: TaskiqMessage) -> int | None:
        """Extract job_id from task message arguments."""
        # Check positional args
        if message.args:
            first_arg = message.args[0]
            # Could be job_id directly or a dict with job_id
            if isinstance(first_arg, int):
                return first_arg
            elif isinstance(first_arg, dict) and "job_id" in first_arg:
                return first_arg["job_id"]

        # Check kwargs
        if "job_id" in message.kwargs:
            return message.kwargs["job_id"]
        if "data" in message.kwargs and isinstance(message.kwargs["data"], dict):
            return message.kwargs["data"].get("job_id")

        return None

    def _format_error(self, error: BaseException | None) -> str:
        """Format error for storage and display."""
        if error is None:
            return "Unknown error"
        return f"{error.__class__.__name__}: {str(error)}"

    async def _mark_job_failed(self, job_id: int, error_message: str) -> None:
        """Mark job as failed in the database."""
        import django

        django.setup()

        from django.utils import timezone

        from core.models import Job, JobStatus

        try:
            job = await Job.objects.aget(id=job_id)
            job.status = JobStatus.FAILED
            job.error_message = error_message
            job.completed_at = timezone.now()
            await job.asave(update_fields=["status", "error_message", "completed_at"])
        except Job.DoesNotExist:
            logger.warning(f"Job {job_id} not found when marking as failed")
        except Exception as e:
            logger.error(f"Failed to update job {job_id}: {e}")

    async def _publish_failure(self, job_id: int, error_message: str) -> None:
        """Publish failure notification to Redis pub/sub."""
        import json
        import os

        import redis.asyncio as aioredis

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

        try:
            redis = await aioredis.from_url(redis_url)
            await redis.publish(
                f"job:{job_id}:progress",
                json.dumps(
                    {
                        "status": "failed",
                        "error": error_message,
                        "progress": 0,
                    }
                ),
            )
            await redis.close()
        except Exception as e:
            logger.error(f"Failed to publish failure for job {job_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to publish failure for job {job_id}: {e}")
