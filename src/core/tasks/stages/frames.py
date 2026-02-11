"""
Frame matching and AI transformation stage tasks.
"""

import asyncio
import os
from typing import cast
from uuid import uuid4

import cv2

from core.storage import (
    S3Storage,
    get_source_key,
    get_source_local_path,
    get_storage_config,
    is_s3_enabled,
    temp_download,
)
from core.tasks.config import FRAME_SCALE_FACTOR, FRAME_SIMILARITY_THRESHOLD, broker
from core.tasks.context import TaskContext
from core.tasks.frames import compare_frames_edges, preprocess_frame_for_comparison
from core.tasks.progress import update_job_progress
from pipeline.ai import clean_transcript
from pipeline.helpers import Caption


@broker.task
async def match_frames_task(data: dict) -> dict:
    """Match frames to captions based on structural similarity."""

    ctx = TaskContext.from_dict(data)
    job_id = ctx.job_id
    user_id = ctx.user_id
    stage_name = "match_frames"

    await update_job_progress(job_id, stage_name, 0, "Matching frames")

    if not ctx.captions:
        ctx.slides = []
        await update_job_progress(job_id, stage_name, 1.0, "Frames matched")
        return ctx.to_dict()

    captions = [Caption(**c) for c in ctx.captions]

    # Get video path - may need to download from S3
    video_path = ctx.get_video_path()

    # For S3, download video to temp location for OpenCV processing
    if is_s3_enabled():
        async with temp_download(video_path) as local_video:
            pairs = await _process_video_frames(
                local_video, captions, user_id, ctx.source_id, job_id, stage_name
            )
    else:
        pairs = await _process_video_frames(
            video_path, captions, user_id, ctx.source_id, job_id, stage_name
        )

    ctx.slides = pairs

    await update_job_progress(job_id, stage_name, 1.0, "Frames matched")

    return ctx.to_dict()


async def _process_video_frames(
    video_path: str,
    captions: list[Caption],
    user_id: int,
    source_id: str,
    job_id: int,
    stage_name: str,
) -> list[dict]:
    """Process video frames and match with captions.

    Args:
        video_path: Local path to video file
        captions: List of captions to match
        user_id: User ID for organizing frames
        source_id: Source ID for organizing frames
        job_id: Job ID for progress updates
        stage_name: Stage name for progress updates

    Returns:
        List of slide dictionaries with image paths and captions
    """
    last_frame = None
    last_frame_gs = None
    cum_captions = []
    pairs = []
    local_frames = []  # Collect frames for batch upload

    stream = cv2.VideoCapture()
    stream.open(video_path)

    # Create local directory for frames
    frame_dir = os.path.dirname(get_source_local_path(user_id, source_id, "frame.jpg"))
    os.makedirs(frame_dir, exist_ok=True)

    try:
        for idx, cap in enumerate(captions):
            # Set video position to caption timestamp + 1.5s offset
            stream.set(cv2.CAP_PROP_POS_MSEC, cap.timestamp * 1_000 + 500)
            ret, frame = stream.read()
            if not ret:
                continue

            # Downscale and convert to grayscale for comparison
            frame_gs = preprocess_frame_for_comparison(frame, FRAME_SCALE_FACTOR)

            if last_frame is None:
                last_frame = frame
                last_frame_gs = frame_gs
                cum_captions.append(cap.text)
                continue

            # Edge-based comparison (works well for lecture slides)
            score = compare_frames_edges(last_frame_gs, frame_gs)

            # Threshold for edge correlation (0.92 = significant structural change)
            if score < FRAME_SIMILARITY_THRESHOLD or (idx + 1) == len(captions):
                cap_full = " ".join(cum_captions)

                # Save frame locally first
                frame_filename = f"{uuid4()}.jpg"
                local_frame_path = get_source_local_path(user_id, source_id, frame_filename)
                cv2.imwrite(local_frame_path, last_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

                # Collect frame info for batch upload
                local_frames.append((local_frame_path, cap_full, frame_filename))
                last_frame = frame
                last_frame_gs = frame_gs
                cum_captions.clear()

                progress = (idx + 1) / len(captions)
                await update_job_progress(job_id, stage_name, progress * 0.9, "Matching slides")

            cum_captions.append(cap.text)

    finally:
        stream.release()

    # Batch upload frames to S3 if enabled
    if is_s3_enabled() and local_frames:
        config = get_storage_config()
        storage = S3Storage(config)

        # Parallelize S3 uploads with rate limiting
        MAX_CONCURRENT_UPLOADS = 8
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_UPLOADS)
        completed_count = 0

        async def upload_frame(idx: int, local_path: str, caption: str, filename: str):
            nonlocal completed_count
            async with semaphore:
                s3_key = get_source_key(user_id, source_id, filename)
                await storage.upload_file(local_path, s3_key, content_type="image/jpeg")

                # Thread-safe progress update
                completed_count += 1
                if idx % 5 == 0:
                    progress = 0.9 + (completed_count / len(local_frames)) * 0.1
                    await update_job_progress(
                        job_id, stage_name, progress, f"Uploading frames ({completed_count}/{len(local_frames)})"
                    )

                return {"image": s3_key, "caption": caption, "extra": None}

        # Process all uploads concurrently
        tasks = [upload_frame(i, path, cap, fname) for i, (path, cap, fname) in enumerate(local_frames)]
        pairs = await asyncio.gather(*tasks)
    else:
        # Local storage - use local paths
        pairs = [{"image": local_path, "caption": caption, "extra": None} for local_path, caption, _ in local_frames]

    return pairs


@broker.task
async def transform_slides_ai_task(data: dict) -> dict:
    """Apply AI transformation to slides with concurrent processing."""
    ctx = TaskContext.from_dict(data)
    job_id = ctx.job_id
    stage_name = "transform_slides_with_ai"

    await update_job_progress(job_id, stage_name, 0, "Transforming slides with AI")

    if not ctx.use_ai or not ctx.slides:
        return ctx.to_dict()

    user_id = ctx.user_id
    slides = cast(list[dict], ctx.slides)
    total = len(slides)

    # Parallelize AI calls with rate limiting
    MAX_CONCURRENT_AI_CALLS = 2  # Respect OpenAI rate limits
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_AI_CALLS)
    completed_count = 0

    async def transform_slide(slide: dict):
        nonlocal completed_count
        async with semaphore:
            cleaned = await clean_transcript(
                slide["caption"],
                user_id=user_id,
                job_id=job_id
            )

            # Thread-safe progress update
            completed_count += 1
            progress = completed_count / total
            await update_job_progress(
                job_id, stage_name,
                progress * 0.9,
                f"Cleaning transcript ({completed_count}/{total})"
            )

            return {
                "image": slide["image"],
                "caption": cleaned,
                "extra": slide.get("extra"),
            }

    # Process all slides concurrently
    tasks = [transform_slide(slide) for slide in slides]
    output = await asyncio.gather(*tasks)

    ctx.slides = output

    await update_job_progress(job_id, stage_name, 1.0, "Slides transformed")

    return ctx.to_dict()
