"""
Job finalization stage task.
"""

from core.tasks.config import broker
from core.tasks.context import TaskContext
from core.tasks.progress import mark_job_completed


@broker.task
async def finalize_job_task(data: dict) -> dict:
    """Finalize the job and create database records."""
    ctx = TaskContext.from_dict(data)
    job_id = ctx.job_id

    outputs = ctx.outputs or {}
    outputs["source_id"] = ctx.source_id

    await mark_job_completed(job_id, outputs)

    return {"job_id": job_id, "status": "completed", "outputs": outputs}
