"""
Artifact generation stage tasks (spreadsheet, vignette, mindmap).
"""

import asyncio
import logging
import os

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from xhtml2pdf import pisa

from core.tasks.config import OUT_DIR, broker
from core.tasks.context import TaskContext
from core.tasks.db import create_artifact
from core.tasks.progress import update_job_progress
from pipeline.ai import generate_mindmap, generate_spreadsheet_helper, generate_vignette_questions
from pipeline.helpers import parse_markdown_bold_to_rich_text


@broker.task
async def generate_spreadsheet_artifact_task(data: dict) -> dict:
    """Generate Excel spreadsheet artifact as a distributed task.

    Returns dict with xlsx_path if successful, empty dict if skipped/failed.
    """
    ctx = TaskContext.from_dict(data)
    job_id = ctx.job_id

    if not ctx.enable_excel:
        return {}

    if ctx.outputs is None:
        return {}

    pdf_path = ctx.outputs.get("pdf_path")
    if not pdf_path or not os.path.exists(pdf_path):
        return {}

    try:
        study_table = await generate_spreadsheet_helper(
            pdf_path,
            custom_prompt=ctx.spreadsheet_prompt,
            custom_columns=ctx.spreadsheet_columns,
        )

        if not study_table.rows:
            return {}

        df = pd.DataFrame(study_table.rows)

        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        output_filename = os.path.join(OUT_DIR, f"{base_name}.xlsx")

        # Style constants
        HEADER_BG_COLOR = "D3D3D3"
        CELL_BG_COLOR = "ADD8E6"
        SECTION_HEADER_BG_COLOR = "6CB4E8"
        BORDER_COLOR = "000000"

        thin_border = Border(
            left=Side(style="thin", color=BORDER_COLOR),
            right=Side(style="thin", color=BORDER_COLOR),
            top=Side(style="thin", color=BORDER_COLOR),
            bottom=Side(style="thin", color=BORDER_COLOR),
        )

        wb = Workbook()
        ws = wb.active
        assert ws is not None

        ws.title = "Study Table"

        # Write header row
        for col_num, column_name in enumerate(df.columns, 1):
            cell = ws.cell(row=1, column=col_num, value=column_name)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(
                start_color=HEADER_BG_COLOR, end_color=HEADER_BG_COLOR, fill_type="solid"
            )
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.border = thin_border

        # Write data rows
        for row_num, row_data in enumerate(study_table.rows, 2):
            first_cell_value = list(row_data.values())[0] if row_data else ""
            is_section_header = all(
                v == "" or v == first_cell_value for v in list(row_data.values())
            )

            for col_num, column_name in enumerate(df.columns, 1):
                cell_value = row_data.get(column_name, "")

                if is_section_header and col_num == 1:
                    cell = ws.cell(row=row_num, column=col_num, value=first_cell_value)
                    cell.font = Font(bold=True)
                    cell.fill = PatternFill(
                        start_color=SECTION_HEADER_BG_COLOR,
                        end_color=SECTION_HEADER_BG_COLOR,
                        fill_type="solid",
                    )
                    ws.merge_cells(
                        start_row=row_num,
                        start_column=1,
                        end_row=row_num,
                        end_column=len(df.columns),
                    )
                    for merged_col in range(1, len(df.columns) + 1):
                        merged_cell = ws.cell(row=row_num, column=merged_col)
                        merged_cell.border = thin_border
                    break
                else:
                    rich_text = parse_markdown_bold_to_rich_text(str(cell_value))
                    cell = ws.cell(row=row_num, column=col_num)
                    cell.value = rich_text
                    cell.fill = PatternFill(
                        start_color=CELL_BG_COLOR, end_color=CELL_BG_COLOR, fill_type="solid"
                    )
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
                    cell.border = thin_border

        # Auto-adjust column widths
        for col_num in range(1, len(df.columns) + 1):
            column_letter = get_column_letter(col_num)
            max_length = 0
            for row in ws.iter_rows(min_col=col_num, max_col=col_num):
                for cell in row:
                    try:
                        cell_length = len(str(cell.value)) if cell.value else 0
                        max_length = max(max_length, cell_length)
                    except Exception:
                        pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width

        await asyncio.to_thread(wb.save, output_filename)

        # Create artifact
        from core.models import ArtifactType

        await create_artifact(
            job_id, ArtifactType.EXCEL_STUDY_TABLE, output_filename, ctx.source_id
        )

        return {"xlsx_path": output_filename}
    except Exception as e:
        logging.exception(f"Failed to generate spreadsheet: {e}")
        return {}


@broker.task
async def generate_vignette_artifact_task(data: dict) -> dict:
    """Generate vignette PDF artifact as a distributed task.

    Returns dict with vignette_path if successful, empty dict if skipped/failed.
    """
    ctx = TaskContext.from_dict(data)
    job_id = ctx.job_id

    if not ctx.enable_vignette:
        return {}

    if ctx.outputs is None:
        return {}

    pdf_path = ctx.outputs.get("pdf_path")
    if not pdf_path or not os.path.exists(pdf_path):
        return {}

    try:
        vignette_data = await generate_vignette_questions(
            pdf_path,
            custom_prompt=ctx.vignette_prompt,
        )

        if not vignette_data.learning_objectives:
            return {}

        learning_objectives = [lo.model_dump() for lo in vignette_data.learning_objectives]

        template_path = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "pdf")
        env = Environment(loader=FileSystemLoader(template_path), autoescape=select_autoescape())
        template = env.get_template("vignette.html")
        html = template.render(learning_objectives=learning_objectives)

        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        vignette_pdf_path = os.path.join(OUT_DIR, f"{base_name} - Vignette Questions.pdf")

        with open(vignette_pdf_path, "wb") as f:
            pisa_status = pisa.CreatePDF(html, dest=f)
            if hasattr(pisa_status, "err") and getattr(pisa_status, "err", None):
                return {}

        # Create artifact
        from core.models import ArtifactType

        await create_artifact(job_id, ArtifactType.PDF_VIGNETTE, vignette_pdf_path, ctx.source_id)

        return {"vignette_path": vignette_pdf_path}
    except Exception as e:
        logging.exception(f"Failed to generate vignette: {e}")
        return {}


@broker.task
async def generate_mindmap_artifact_task(data: dict) -> dict:
    """Generate mindmap Mermaid file(s) as a distributed task.

    Returns dict with mindmap_paths (list) if successful, empty dict if skipped/failed.
    """
    ctx = TaskContext.from_dict(data)
    job_id = ctx.job_id

    if not ctx.enable_mindmap:
        return {}

    if ctx.outputs is None:
        return {}

    pdf_path = ctx.outputs.get("pdf_path")
    if not pdf_path or not os.path.exists(pdf_path):
        return {}

    try:
        mindmaps = await generate_mindmap(
            pdf_path,
            custom_prompt=ctx.mindmap_prompt,
        )

        if not mindmaps:
            return {}

        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        mindmap_paths = []

        # Create artifact import
        from core.models import ArtifactType

        for i, (title, mermaid_code) in enumerate(mindmaps):
            # Sanitize title for filename
            safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
            if not safe_title:
                safe_title = f"Mindmap {i + 1}"

            # If only one mindmap, use simpler naming
            if len(mindmaps) == 1:
                mindmap_path = os.path.join(OUT_DIR, f"{base_name} - {safe_title}.mmd")
            else:
                mindmap_path = os.path.join(OUT_DIR, f"{base_name} - {safe_title}.mmd")

            # Save mermaid code as text file
            with open(mindmap_path, "w", encoding="utf-8") as f:
                f.write(mermaid_code)

            # Create artifact for each mindmap
            await create_artifact(job_id, ArtifactType.MERMAID_MINDMAP, mindmap_path, ctx.source_id)
            mindmap_paths.append(mindmap_path)

        return {"mindmap_paths": mindmap_paths}
    except Exception as e:
        logging.exception(f"Failed to generate mindmap: {e}")
        return {}


@broker.task
async def generate_artifacts_task(data: dict) -> dict:
    """Generate all artifacts (spreadsheet, vignette, mindmap) in parallel using distributed tasks."""
    ctx = TaskContext.from_dict(data)
    job_id = ctx.job_id
    stage_name = "generate_artifacts"

    await update_job_progress(job_id, stage_name, 0, "Generating artifacts")

    if ctx.outputs is None:
        ctx.outputs = {}

    pdf_path = ctx.outputs.get("pdf_path")
    if not pdf_path or not os.path.exists(pdf_path):
        return ctx.to_dict()

    # Queue all tasks with their names for progress reporting
    tasks_with_names = [
        (await generate_spreadsheet_artifact_task.kiq(data), "Spreadsheet"),
        (await generate_vignette_artifact_task.kiq(data), "Vignette"),
        (await generate_mindmap_artifact_task.kiq(data), "Mindmap"),
    ]

    await update_job_progress(job_id, stage_name, 0.1, "Waiting for artifact tasks")

    # Wait for results as they complete and report progress
    completed_count = 0
    total_tasks = len(tasks_with_names)

    # Create futures for each task's wait_result
    async def wait_and_identify(task_handle, name: str):
        result = await task_handle.wait_result()
        return (result, name)

    pending = [
        asyncio.create_task(wait_and_identify(task, name)) for task, name in tasks_with_names
    ]

    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

        for completed_task in done:
            try:
                result, task_name = await completed_task
                completed_count += 1

                # Calculate progress (0.1 to 0.9 range for artifact generation)
                progress = 0.1 + (completed_count / total_tasks) * 0.8

                # Check if task succeeded
                if result is not None and not result.is_err:
                    return_value = getattr(result, "return_value", None)
                    if isinstance(return_value, dict) and return_value:
                        ctx.outputs.update(return_value)
                        await update_job_progress(
                            job_id,
                            stage_name,
                            progress,
                            f"{task_name} completed ({completed_count}/{total_tasks})",
                        )
                    else:
                        await update_job_progress(
                            job_id,
                            stage_name,
                            progress,
                            f"{task_name} skipped ({completed_count}/{total_tasks})",
                        )
                else:
                    await update_job_progress(
                        job_id,
                        stage_name,
                        progress,
                        f"{task_name} failed ({completed_count}/{total_tasks})",
                    )
                    if result is not None and result.is_err:
                        logging.error(f"{task_name} artifact generation failed: {result.error}")

            except Exception as e:
                completed_count += 1
                progress = 0.1 + (completed_count / total_tasks) * 0.8
                logging.exception(f"Artifact task failed: {e}")
                await update_job_progress(
                    job_id, stage_name, progress, f"Task failed ({completed_count}/{total_tasks})"
                )

        # Convert remaining pending set back to list for next iteration
        pending = set(pending)

    await update_job_progress(job_id, stage_name, 1.0, "Artifacts generated")

    return ctx.to_dict()
