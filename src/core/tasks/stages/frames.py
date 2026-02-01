"""
Frame matching and AI transformation stage tasks.
"""

import os
from typing import cast
from uuid import uuid4

import cv2

from core.tasks.config import FRAME_SCALE_FACTOR, FRAME_SIMILARITY_THRESHOLD, FRAMES_DIR, broker
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
    stage_name = "match_frames"

    await update_job_progress(job_id, stage_name, 0, "Matching frames")

    if not ctx.captions:
        ctx.slides = []
        await update_job_progress(job_id, stage_name, 1.0, "Frames matched")
        return ctx.to_dict()

    captions = [Caption(**c) for c in ctx.captions]
    last_frame = None
    last_frame_gs = None
    cum_captions = []
    pairs = []

    stream = cv2.VideoCapture()
    stream.open(ctx.get_video_path())

    frame_path = os.path.join(FRAMES_DIR, ctx.source_id)
    os.makedirs(frame_path, exist_ok=True)

    for idx, cap in enumerate(captions):
        # Set video position to caption timestamp + 1.5s offset
        stream.set(cv2.CAP_PROP_POS_MSEC, cap.timestamp * 1_500)
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
            # Option 4: Use JPEG format for faster I/O
            image_path = os.path.join(frame_path, f"{uuid4()}.jpg")
            cv2.imwrite(image_path, last_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

            pairs.append({"image": image_path, "caption": cap_full, "extra": None})
            last_frame = frame
            last_frame_gs = frame_gs
            cum_captions.clear()

            progress = (idx + 1) / len(captions)
            await update_job_progress(job_id, stage_name, progress * 0.9, "Matching slides")

        cum_captions.append(cap.text)

    stream.release()
    ctx.slides = pairs

    await update_job_progress(job_id, stage_name, 1.0, "Frames matched")

    return ctx.to_dict()


@broker.task
async def transform_slides_ai_task(data: dict) -> dict:
    """Apply AI transformation to slides."""
    ctx = TaskContext.from_dict(data)
    job_id = ctx.job_id
    stage_name = "transform_slides_with_ai"

    await update_job_progress(job_id, stage_name, 0, "Transforming slides with AI")

    if not ctx.use_ai or not ctx.slides:
        return ctx.to_dict()

    output = []
    slides = cast(list[dict], ctx.slides)
    total = len(slides)

    for idx, slide in enumerate(slides):
        cleaned = await clean_transcript(slide["caption"])
        output.append(
            {
                "image": slide["image"],
                "caption": cleaned,
                "extra": slide.get("extra"),
            }
        )

        progress = (idx + 1) / total
        await update_job_progress(job_id, stage_name, progress * 0.9, "Cleaning transcript")

    ctx.slides = output

    await update_job_progress(job_id, stage_name, 1.0, "Slides transformed")

    return ctx.to_dict()
