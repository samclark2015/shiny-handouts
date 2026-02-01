"""Main views for the dashboard and file serving."""

import os

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render

from core.models import Artifact, ArtifactType, Job, JobStatus, Lecture
from core.storage import (
    download_bytes,
    generate_presigned_url,
    is_s3_enabled,
    sync_download_file,
    sync_file_exists,
)


@login_required
def index(request):
    """Main page with file upload and task list."""
    # Get user's active jobs only
    jobs = (
        Job.objects.filter(user=request.user)
        .filter(
            status__in=[JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED, JobStatus.CANCELLED]
        )
        .order_by("-created_at")[:50]
    )

    # Get user's lectures grouped by date
    lectures = Lecture.objects.filter(user=request.user).order_by("-date")

    # Group lectures by date
    lectures_by_date = {}
    for lecture in lectures:
        date_key = lecture.date.strftime("%Y-%m-%d")
        if date_key not in lectures_by_date:
            lectures_by_date[date_key] = []
        lectures_by_date[date_key].append(lecture)

    # Get user's setting profiles
    from accounts.models import SettingProfile

    profiles = SettingProfile.objects.filter(user=request.user).order_by("name")
    default_profile = profiles.filter(is_default=True).first()

    return render(
        request,
        "index.html",
        {
            "jobs": jobs,
            "lectures_by_date": lectures_by_date,
            "user": request.user,
            "profiles": profiles,
            "default_profile": default_profile,
        },
    )


@login_required
def serve_file(request, filename: str):
    """Serve generated files from storage (local or S3)."""
    if is_s3_enabled():
        # For S3, generate a presigned URL and redirect
        s3_key = f"{settings.S3_OUTPUT_PREFIX}{filename}"

        # Verify the artifact exists and belongs to user
        artifact = Artifact.objects.filter(
            file_name=filename,
            lecture__user=request.user,
        ).first()

        if not artifact:
            raise Http404("File not found")

        # Generate presigned URL with download disposition
        presigned_url = async_to_sync(generate_presigned_url)(
            artifact.file_path,
            expiration=3600,
            response_content_disposition=f'attachment; filename="{filename}"',
        )
        return HttpResponseRedirect(presigned_url)

    # Local storage
    file_path = os.path.join(settings.OUTPUT_DIR, filename)

    if not os.path.exists(file_path):
        raise Http404("File not found")

    # Security check: ensure file is within OUTPUT_DIR
    real_path = os.path.realpath(file_path)
    real_output_dir = os.path.realpath(settings.OUTPUT_DIR)

    if not real_path.startswith(real_output_dir):
        raise Http404("File not found")

    return FileResponse(
        open(file_path, "rb"),
        as_attachment=True,
        filename=os.path.basename(filename),
    )


@login_required
def render_mindmap(request, filename: str):
    """Render a Mermaid mindmap file in the browser."""
    # Only allow .mmd files
    if not filename.endswith(".mmd"):
        raise Http404("File not found")

    # Get the mermaid code
    mermaid_code = _get_file_content(request.user, filename)
    if mermaid_code is None:
        raise Http404("File not found")

    # Get the title from the filename
    title = os.path.splitext(os.path.basename(filename))[0]

    return render(
        request,
        "mindmap.html",
        {
            "mermaid_code": mermaid_code,
            "title": title,
        },
    )


def _get_file_content(user, filename: str) -> str | None:
    """Get file content from storage (local or S3).

    Args:
        user: The requesting user (for access control)
        filename: The filename to retrieve

    Returns:
        File content as string, or None if not found
    """
    if is_s3_enabled():
        # For S3, find the artifact and download content
        artifact = Artifact.objects.filter(
            file_name=filename,
            lecture__user=user,
        ).first()

        if not artifact:
            return None

        try:
            content_bytes = async_to_sync(download_bytes)(artifact.file_path)
            return content_bytes.decode("utf-8")
        except Exception:
            return None

    # Local storage
    file_path = os.path.join(settings.OUTPUT_DIR, filename)

    if not os.path.exists(file_path):
        return None

    # Security check: ensure file is within OUTPUT_DIR
    real_path = os.path.realpath(file_path)
    real_output_dir = os.path.realpath(settings.OUTPUT_DIR)

    if not real_path.startswith(real_output_dir):
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


@login_required
def lecture_mindmaps(request, lecture_id: int):
    """Display all mindmaps for a given lecture."""
    lecture = get_object_or_404(Lecture, id=lecture_id, user=request.user)

    # Get all mindmap artifacts for this lecture
    mindmap_artifacts = lecture.artifacts.filter(artifact_type=ArtifactType.MERMAID_MINDMAP)

    # Read the mermaid code for each mindmap
    mindmaps = []
    for artifact in mindmap_artifacts:
        mermaid_code = _get_artifact_content(artifact)
        if mermaid_code:
            # Extract title from filename (remove base lecture name prefix if present)
            title = os.path.splitext(artifact.file_name)[0]
            # Try to get just the mindmap-specific part after " - "
            if " - " in title:
                parts = title.split(" - ")
                if len(parts) > 1:
                    title = parts[-1]  # Get the last part (mindmap title)
            mindmaps.append(
                {
                    "title": title,
                    "mermaid_code": mermaid_code,
                    "artifact": artifact,
                }
            )

    return render(
        request,
        "lecture_mindmaps.html",
        {
            "lecture": lecture,
            "mindmaps": mindmaps,
        },
    )


def _get_artifact_content(artifact: Artifact) -> str | None:
    """Get artifact file content from storage.

    Args:
        artifact: The artifact to retrieve content for

    Returns:
        File content as string, or None if not found
    """
    if is_s3_enabled():
        try:
            content_bytes = async_to_sync(download_bytes)(artifact.file_path)
            return content_bytes.decode("utf-8")
        except Exception:
            return None

    # Local storage
    file_path = os.path.join(settings.OUTPUT_DIR, artifact.file_name)
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    return None
