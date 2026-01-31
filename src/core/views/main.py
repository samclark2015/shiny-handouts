"""Main views for the dashboard and file serving."""

import os

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render

from core.models import ArtifactType, Job, JobStatus, Lecture


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
    """Serve generated files."""
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

    file_path = os.path.join(settings.OUTPUT_DIR, filename)

    if not os.path.exists(file_path):
        raise Http404("File not found")

    # Security check: ensure file is within OUTPUT_DIR
    real_path = os.path.realpath(file_path)
    real_output_dir = os.path.realpath(settings.OUTPUT_DIR)

    if not real_path.startswith(real_output_dir):
        raise Http404("File not found")

    # Read the mermaid code
    with open(file_path, "r", encoding="utf-8") as f:
        mermaid_code = f.read()

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


@login_required
def lecture_mindmaps(request, lecture_id: int):
    """Display all mindmaps for a given lecture."""
    lecture = get_object_or_404(Lecture, id=lecture_id, user=request.user)

    # Get all mindmap artifacts for this lecture
    mindmap_artifacts = lecture.artifacts.filter(artifact_type=ArtifactType.MERMAID_MINDMAP)

    # Read the mermaid code for each mindmap
    mindmaps = []
    for artifact in mindmap_artifacts:
        file_path = os.path.join(settings.OUTPUT_DIR, artifact.file_name)
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                mermaid_code = f.read()
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
