"""
Video download and caption extraction stage tasks.
"""

import os

from core.storage import file_exists, get_source_local_path, get_source_path, is_s3_enabled
from core.tasks.config import broker
from core.tasks.context import TaskContext
from core.tasks.db import update_job_source_info
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
    user_id = ctx.user_id
    stage_name = "download_video"

    await update_job_progress(job_id, stage_name, 0, "Checking video")

    # For uploads, handle the path from input_data
    if ctx.input_type == "upload":
        upload_path = ctx.input_data.get("path", "")
        # Check if file exists (local or S3)
        if upload_path and await file_exists(upload_path):
                ctx.video_path = upload_path
                await update_job_progress(job_id, stage_name, 1.0, "Video ready")
                return ctx.to_dict()

    # Check if video already exists for this source (reuse from previous job)
    video_filename = "video.mp4"
    storage_path = get_source_path(user_id, ctx.source_id, video_filename)

    if await file_exists(storage_path):
        ctx.video_path = storage_path
        await update_job_progress(job_id, stage_name, 1.0, "Video ready (reused)")
        return ctx.to_dict()

    # For URL/Panopto downloads, use local temp storage then optionally upload to S3
    local_video_path = get_source_local_path(user_id, ctx.source_id, video_filename)
    os.makedirs(os.path.dirname(local_video_path), exist_ok=True)

    if ctx.input_type == "panopto":
        await download_panopto_video(job_id, stage_name, ctx.input_data, local_video_path)
    else:
        video_url = ctx.input_data.get("url", "")
        if is_m3u8_url(video_url):
            await download_m3u8_stream(job_id, stage_name, video_url, local_video_path)
        else:
            await download_regular_video(job_id, stage_name, video_url, local_video_path)

        # Hash the downloaded file contents to generate source_id
        new_source_id = await hash_file(local_video_path)
        if new_source_id != ctx.source_id:
            ctx.source_id = new_source_id
            await update_job_source_info(job_id, new_source_id)
            # Move file to correct location with new source_id
            new_local_path = get_source_local_path(user_id, new_source_id, video_filename)
            os.makedirs(os.path.dirname(new_local_path), exist_ok=True)
            os.rename(local_video_path, new_local_path)
            local_video_path = new_local_path

    # Upload to S3 if enabled
    if is_s3_enabled():
        from core.storage import get_s3_client, get_source_key, get_storage_config

        config = get_storage_config()
        s3_key = get_source_key(user_id, ctx.source_id, video_filename)

        async with get_s3_client() as s3:
            await s3.upload_file(local_video_path, config.bucket_name, s3_key)

        ctx.video_path = s3_key
    else:
        ctx.video_path = local_video_path

    # Update job with video path
    await update_job_source_info(job_id, ctx.source_id, video_path=ctx.video_path)

    await update_job_progress(job_id, stage_name, 1.0, "Video downloaded")

    return ctx.to_dict()

    return ctx.to_dict()


@broker.task
async def extract_captions_task(data: dict) -> dict:
    """Extract captions from the video."""
    from core.storage import temp_download

    ctx = TaskContext.from_dict(data)
    job_id = ctx.job_id
    stage_name = "extract_captions"

    await update_job_progress(job_id, stage_name, 0, "Extracting captions")

    video_path = ctx.get_video_path()

    # For S3, download video to temp location for caption extraction
    if is_s3_enabled():
        async with temp_download(video_path) as local_video:
            captions = await generate_captions(local_video)
    else:
        captions = await generate_captions(video_path)

    ctx.captions = [{"text": c.text, "timestamp": c.timestamp} for c in captions]

    await update_job_progress(job_id, stage_name, 1.0, "Captions extracted")

    return ctx.to_dict()
