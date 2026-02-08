"""
Pipeline creation and execution functions.
"""

from taskiq_pipelines import Pipeline

from .config import broker
from .stages import (
    compress_pdf_task,
    download_video_task,
    extract_captions_task,
    extract_images_task,
    finalize_job_task,
    generate_artifacts_task,
    generate_context_task,
    generate_output_task,
    match_frames_task,
    transform_slides_ai_task,
)


def create_pipeline(job_id: int, input_type: str, input_data: str) -> Pipeline:
    """Create a taskiq Pipeline for the full processing chain."""
    return (
        Pipeline(broker, generate_context_task)
        .call_next(download_video_task)
        .call_next(extract_captions_task)
        .call_next(match_frames_task)
        .call_next(extract_images_task)
        .call_next(transform_slides_ai_task)
        .call_next(generate_output_task)
        .call_next(compress_pdf_task)
        .call_next(generate_artifacts_task)
        .call_next(finalize_job_task)
    )


async def start_pipeline(job_id: int, input_type: str, input_data: str) -> str:
    """Start the pipeline and return the Taskiq task ID."""
    pipeline = create_pipeline(job_id, input_type, input_data)
    task = await pipeline.kiq(job_id, input_type, input_data)
    return task.task_id
