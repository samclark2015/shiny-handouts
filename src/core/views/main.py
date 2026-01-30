"""Main views for the dashboard and file serving."""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import render

from core.models import Job, JobStatus, Lecture


@login_required
def index(request):
    """Main page with file upload and task list."""
    # Get user's active jobs only
    jobs = (
        Job.objects.filter(user=request.user)
        .filter(status__in=[JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED])
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

    return render(
        request,
        "index.html",
        {
            "jobs": jobs,
            "lectures_by_date": lectures_by_date,
            "user": request.user,
        },
    )


@login_required
def serve_file(request, filename: str):
    """Serve generated files."""
    import os

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
