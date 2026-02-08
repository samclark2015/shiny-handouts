"""
Image extraction stage task.

Extracts images from slides after frame matching, preparing them
for use in spreadsheet generation.
"""

import asyncio
import logging
import os

from core.storage import (
    S3Storage,
    get_source_key,
    get_source_local_path,
    get_storage_config,
    is_s3_enabled,
    temp_download,
)
from core.tasks.config import broker
from core.tasks.context import TaskContext
from core.tasks.progress import update_job_progress
from pipeline.image_extraction import (
    ExtractedImage,
    extract_images_from_slide,
    filter_images_by_size,
)

logger = logging.getLogger(__name__)


@broker.task
async def extract_images_task(data: dict) -> dict:
    """Extract images from all slides in the pipeline.

    This stage runs after match_frames_task and before transform_slides_ai_task.
    It extracts figures/diagrams from each slide frame and stores them
    for later use in spreadsheet generation.
    """
    ctx = TaskContext.from_dict(data)
    job_id = ctx.job_id
    user_id = ctx.user_id
    source_id = ctx.source_id
    stage_name = "extract_images"

    await update_job_progress(job_id, stage_name, 0, "Extracting images from slides")

    if not ctx.slides:
        ctx.extracted_images = []
        await update_job_progress(job_id, stage_name, 1.0, "No slides to process")
        return ctx.to_dict()

    # Create local output directory for extracted images
    extracted_dir = get_source_local_path(user_id, source_id, "extracted")
    extracted_dir = os.path.dirname(extracted_dir)
    extracted_images_dir = os.path.join(extracted_dir, "extracted_images")
    os.makedirs(extracted_images_dir, exist_ok=True)

    all_extracted: list[ExtractedImage] = []
    total_slides = len(ctx.slides)

    # Process slides with concurrency limit
    MAX_CONCURRENT = 4
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    completed_count = 0

    async def process_slide(slide_idx: int, slide: dict) -> list[ExtractedImage]:
        nonlocal completed_count
        async with semaphore:
            slide_image_path = slide.get("image", "")
            if not slide_image_path:
                return []

            try:
                # If S3, download the slide frame temporarily
                if is_s3_enabled():
                    async with temp_download(slide_image_path) as local_slide:
                        extracted = await extract_images_from_slide(
                            local_slide,
                            slide_idx,
                            extracted_images_dir,
                            min_area_ratio=0.02,
                            max_area_ratio=0.7,
                            max_images_per_slide=5,
                            max_size_kb=200,
                        )
                else:
                    extracted = await extract_images_from_slide(
                        slide_image_path,
                        slide_idx,
                        extracted_images_dir,
                        min_area_ratio=0.02,
                        max_area_ratio=0.7,
                        max_images_per_slide=5,
                        max_size_kb=200,
                    )

                completed_count += 1
                progress = completed_count / total_slides * 0.8
                await update_job_progress(
                    job_id,
                    stage_name,
                    progress,
                    f"Processed slide {completed_count}/{total_slides}",
                )
                return extracted

            except Exception as e:
                logger.warning(f"Failed to extract images from slide {slide_idx}: {e}")
                completed_count += 1
                return []

    # Process all slides concurrently
    tasks = [process_slide(idx, slide) for idx, slide in enumerate(ctx.slides)]
    results = await asyncio.gather(*tasks)

    for extracted_list in results:
        all_extracted.extend(extracted_list)

    logger.info(f"Extracted {len(all_extracted)} images from {total_slides} slides")

    # Filter images to stay under 45MB total for LLM context
    all_extracted = filter_images_by_size(all_extracted, max_total_mb=45.0)
    logger.info(f"After filtering: {len(all_extracted)} images")

    # Upload extracted images to S3 if enabled
    if is_s3_enabled() and all_extracted:
        await update_job_progress(job_id, stage_name, 0.85, "Uploading extracted images")

        config = get_storage_config()
        storage = S3Storage(config)

        upload_semaphore = asyncio.Semaphore(8)

        async def upload_image(img: ExtractedImage) -> ExtractedImage:
            async with upload_semaphore:
                local_path = img.path
                filename = os.path.basename(local_path)
                s3_key = get_source_key(user_id, source_id, f"extracted/{filename}")
                await storage.upload_file(local_path, s3_key, content_type="image/jpeg")
                # Update path to S3 key
                return ExtractedImage(
                    slide_index=img.slide_index,
                    region_index=img.region_index,
                    label=img.label,
                    confidence=img.confidence,
                    bbox=img.bbox,
                    width=img.width,
                    height=img.height,
                    path=s3_key,
                    size_bytes=img.size_bytes,
                )

        upload_tasks = [upload_image(img) for img in all_extracted]
        all_extracted = await asyncio.gather(*upload_tasks)

    # Store extracted images in context
    ctx.extracted_images = [img.to_dict() for img in all_extracted]

    total_size_mb = sum(img.size_bytes for img in all_extracted) / (1024 * 1024)
    await update_job_progress(
        job_id,
        stage_name,
        1.0,
        f"Extracted {len(all_extracted)} images ({total_size_mb:.1f}MB)",
    )

    return ctx.to_dict()
