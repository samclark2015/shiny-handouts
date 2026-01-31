"""
Taskiq tasks for the video processing pipeline.

Converts the pipeline stages into Taskiq tasks with:
- Progress reporting via Redis pub/sub
- Pipeline chaining via taskiq-pipelines

This package is organized into the following modules:
- config: Configuration, constants, and broker setup
- context: TaskContext dataclass for pipeline state
- progress: Progress tracking and job status utilities
- db: Database operations for lectures and artifacts
- video: Video download utilities
- frames: Frame extraction and comparison utilities
- stages/: Pipeline stage task definitions
- pipeline: Pipeline creation and execution
"""

import redis.asyncio as aioredis
from taskiq import TaskiqEvents

from .config import (FRAME_SCALE_FACTOR, FRAME_SIMILARITY_THRESHOLD, REDIS_URL,
                     broker)
from .context import TaskContext
from .frames import compare_frames_edges, preprocess_frame_for_comparison
from .pipeline import create_pipeline, start_pipeline
from .progress import JobCancelledException, check_job_cancelled
# Re-export all stage tasks for backwards compatibility
from .stages import (compress_pdf_task, download_video_task,
                     extract_captions_task, finalize_job_task,
                     generate_artifacts_task, generate_context_task,
                     generate_mindmap_artifact_task, generate_output_task,
                     generate_spreadsheet_artifact_task,
                     generate_vignette_artifact_task, match_frames_task,
                     transform_slides_ai_task)


# Worker lifecycle events
@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def on_worker_startup(state):
    """Initialize resources when worker starts."""
    # Initialize Django before using any models
    import django

    django.setup()

    # Store Redis connection for pub/sub in state
    state.redis = await aioredis.from_url(REDIS_URL)


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def on_worker_shutdown(state):
    """Cleanup when worker shuts down."""
    if hasattr(state, "redis"):
        await state.redis.close()


__all__ = [
    # Core
    "broker",
    "TaskContext",
    "JobCancelledException",
    "check_job_cancelled",
    # Frame utilities
    "FRAME_SCALE_FACTOR",
    "FRAME_SIMILARITY_THRESHOLD",
    "compare_frames_edges",
    "preprocess_frame_for_comparison",
    # Pipeline
    "create_pipeline",
    "start_pipeline",
    # Stage tasks
    "generate_context_task",
    "download_video_task",
    "extract_captions_task",
    "match_frames_task",
    "transform_slides_ai_task",
    "generate_output_task",
    "compress_pdf_task",
    "generate_spreadsheet_artifact_task",
    "generate_vignette_artifact_task",
    "generate_mindmap_artifact_task",
    "generate_artifacts_task",
    "finalize_job_task",
]