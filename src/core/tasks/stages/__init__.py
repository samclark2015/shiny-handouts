"""
Pipeline stage tasks.

This module exports all pipeline stage tasks for use in pipeline construction.
"""

from .artifacts import (
    generate_artifacts_task,
    generate_mindmap_artifact_task,
    generate_spreadsheet_artifact_task,
    generate_vignette_artifact_task,
)
from .context import generate_context_task
from .finalize import finalize_job_task
from .frames import match_frames_task, transform_slides_ai_task
from .output import compress_pdf_task, generate_output_task
from .video import download_video_task, extract_captions_task

__all__ = [
    # Context
    "generate_context_task",
    # Video
    "download_video_task",
    "extract_captions_task",
    # Frames
    "match_frames_task",
    "transform_slides_ai_task",
    # Output
    "generate_output_task",
    "compress_pdf_task",
    # Artifacts
    "generate_spreadsheet_artifact_task",
    "generate_vignette_artifact_task",
    "generate_mindmap_artifact_task",
    "generate_artifacts_task",
    # Finalize
    "finalize_job_task",
]
