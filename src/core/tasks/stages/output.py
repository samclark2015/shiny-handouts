"""
Output generation stage tasks (PDF generation and compression).
"""

import asyncio
import os
import shutil
import subprocess
from tempfile import TemporaryDirectory

from django.conf import settings
from jinja2 import Environment, FileSystemLoader, select_autoescape
from xhtml2pdf import pisa

from core.tasks.config import OUT_DIR, broker
from core.tasks.context import TaskContext
from core.tasks.db import create_artifact
from core.tasks.progress import update_job_label, update_job_progress
from pipeline.ai import generate_title
from pipeline.helpers import Slide


@broker.task
async def generate_output_task(data: dict) -> dict:
    """Generate the PDF output."""
    ctx = TaskContext.from_dict(data)
    job_id = ctx.job_id
    stage_name = "generate_output"

    await update_job_progress(job_id, stage_name, 0, "Generating PDF")

    # Convert slide dicts back to Slide namedtuples for template
    slides = [Slide(**s) for s in ctx.slides] if ctx.slides else []

    template_path = settings.BASE_DIR / "templates" / "pdf"
    env = Environment(loader=FileSystemLoader(template_path), autoescape=select_autoescape())
    template = env.get_template("template.html")
    html = template.render(pairs=slides)

    await update_job_progress(job_id, stage_name, 0.3, "Generating title")
    title = await generate_title(html)
    await update_job_label(job_id, title)

    # Generate PDF locally first
    local_path = os.path.join(OUT_DIR, f"{title}.pdf")
    os.makedirs(OUT_DIR, exist_ok=True)

    await update_job_progress(job_id, stage_name, 0.5, "Creating PDF")
    with open(local_path, "wb") as f:
        pisa_status = pisa.CreatePDF(html, dest=f)
        if hasattr(pisa_status, "err") and getattr(pisa_status, "err", None):
            raise ValueError("Error generating PDF")

    ctx.outputs = ctx.outputs or {}
    ctx.outputs["pdf_local_path"] = local_path
    ctx.outputs["pdf_filename"] = f"{title}.pdf"
    ctx.outputs["source_id"] = ctx.source_id

    await update_job_progress(job_id, stage_name, 1.0, "PDF generated")

    return ctx.to_dict()


@broker.task
async def compress_pdf_task(data: dict) -> dict:
    """Compress the PDF using Ghostscript, then upload and create artifact."""
    ctx = TaskContext.from_dict(data)
    job_id = ctx.job_id
    stage_name = "compress_pdf"

    await update_job_progress(job_id, stage_name, 0, "Compressing PDF")

    if not ctx.outputs:
        return ctx.to_dict()

    pdf_local_path = ctx.outputs.get("pdf_local_path")
    pdf_filename = ctx.outputs.get("pdf_filename", "output.pdf")
    source_id = ctx.outputs.get("source_id", "")

    if not pdf_local_path or not os.path.exists(pdf_local_path):
        return ctx.to_dict()

    # Compress the PDF locally
    await _compress_pdf(pdf_local_path)

    await update_job_progress(job_id, stage_name, 0.7, "Uploading PDF")

    # Upload and create artifact
    from core.models import ArtifactType

    storage_path = await create_artifact(
        job_id,
        ArtifactType.PDF_HANDOUT,
        pdf_filename,
        local_path=pdf_local_path,
        content_type="application/pdf",
        source_id=source_id,
    )

    ctx.outputs["pdf_path"] = storage_path

    await update_job_progress(job_id, stage_name, 1.0, "PDF compressed")

    return ctx.to_dict()


async def _compress_pdf(pdf_path: str) -> str | None:
    """Compress a PDF file using Ghostscript.

    Args:
        pdf_path: Path to the PDF file to compress

    Returns:
        Path to compressed file, or None if compression failed
    """
    with TemporaryDirectory() as temp_dir:
        output_path = os.path.join(temp_dir, f"compressed_{os.path.basename(pdf_path)}")

        gs_command = [
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/ebook",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={output_path}",
            pdf_path,
        ]

        try:
            await asyncio.to_thread(subprocess.run, gs_command, check=True)
            shutil.move(output_path, pdf_path)
            return pdf_path
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Ghostscript compression failed: {e}")
            return None
