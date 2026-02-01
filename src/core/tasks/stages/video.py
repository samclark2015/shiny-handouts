"""
Video download and caption extraction stage tasks.
"""

import os

from core.tasks.config import broker
from core.tasks.context import TaskContext
from core.tasks.progress import update_job_progress
from core.tasks.video import (
    download_m3u8_stream,
    download_panopto_video,
    download_regular_video,
    hash_file,
    is_m3u8_url,
)
from pipeline.ai import generate_captions


@broker.task
async def download_video_task(data: dict) -> dict:
    """Download video if it doesn't exist."""
    ctx = TaskContext.from_dict(data)
    job_id = ctx.job_id
    stage_name = "download_video"

    await update_job_progress(job_id, stage_name, 0, "Checking video")

    video_path = ctx.get_video_path()

    if ctx.input_type == "upload":
        upload_path = ctx.input_data.get("path", "")
        if os.path.exists(upload_path):
            ctx.video_path = upload_path
            await update_job_progress(job_id, stage_name, 1.0, "Video ready")
            return ctx.to_dict()

    if ctx.input_type == "panopto":
        await download_panopto_video(job_id, stage_name, ctx.input_data, video_path)
    else:
        video_url = ctx.input_data.get("url", "")
        if is_m3u8_url(video_url):
            await download_m3u8_stream(job_id, stage_name, video_url, video_path)
        else:
            await download_regular_video(job_id, stage_name, video_url, video_path)

        # Hash the downloaded file contents to generate source_id
        ctx.source_id = await hash_file(video_path)

    ctx.video_path = video_path

    await update_job_progress(job_id, stage_name, 1.0, "Video downloaded")

    return ctx.to_dict()


@broker.task
async def extract_captions_task(data: dict) -> dict:
    """Extract captions from the video."""
    ctx = TaskContext.from_dict(data)
    job_id = ctx.job_id
    stage_name = "extract_captions"

    await update_job_progress(job_id, stage_name, 0, "Extracting captions")

    captions = await generate_captions(ctx.get_video_path())
    ctx.captions = [{"text": c.text, "timestamp": c.timestamp} for c in captions]

    await update_job_progress(job_id, stage_name, 1.0, "Captions extracted")

    return ctx.to_dict()
