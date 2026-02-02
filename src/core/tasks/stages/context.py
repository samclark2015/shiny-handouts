"""
Context generation stage task.
"""

import json
from typing import cast

from core.tasks.config import broker
from core.tasks.context import TaskContext
from core.tasks.db import update_job_source_info
from core.tasks.progress import update_job_progress
from core.tasks.video import hash_file


@broker.task
async def generate_context_task(job_id: int, input_type: str, input_data: str) -> dict:
    """Generate processing context from input."""
    from core.models import Job

    stage_name = "generate_context"

    await update_job_progress(job_id, stage_name, 0, "Initializing")

    input_dict = cast(dict, json.loads(input_data))
    # Generate source_id based on input type
    if input_type == "panopto":
        source_id = input_dict.get("delivery_id", "")
    elif input_type == "url":
        source_id = input_dict.get("url", "")
    else:  # upload
        source_id = await hash_file(input_dict.get("path", ""))

    # Load job settings and profile
    job = await Job.objects.select_related("user", "setting_profile").aget(id=job_id)
    user_id = job.user_id
    enable_excel = job.enable_excel
    enable_vignette = job.enable_vignette
    enable_mindmap = job.enable_mindmap

    # Update job with source_id early
    await update_job_source_info(job_id, source_id)

    # Load settings from profile (if set)
    vignette_prompt = None
    spreadsheet_prompt = None
    spreadsheet_columns = None
    mindmap_prompt = None

    if job.setting_profile:
        vignette_prompt = job.setting_profile.get_vignette_prompt()
        spreadsheet_prompt = job.setting_profile.get_spreadsheet_prompt()
        spreadsheet_columns = job.setting_profile.get_spreadsheet_columns()
        mindmap_prompt = job.setting_profile.get_mindmap_prompt()

    ctx = TaskContext(
        job_id=job_id,
        user_id=user_id,
        source_id=source_id,
        input_type=input_type,
        input_data=input_dict,
        use_ai=True,
        enable_excel=enable_excel,
        enable_vignette=enable_vignette,
        enable_mindmap=enable_mindmap,
        vignette_prompt=vignette_prompt,
        spreadsheet_prompt=spreadsheet_prompt,
        spreadsheet_columns=spreadsheet_columns,
        mindmap_prompt=mindmap_prompt,
    )

    await update_job_progress(job_id, stage_name, 1.0, "Context created")

    return ctx.to_dict()
