"""Main views for the dashboard and file serving."""

import os

from asgiref.sync import async_to_sync
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import render

from core.models import Artifact, ArtifactType, Job, JobStatus
from core.storage import get_storage, is_s3_enabled


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

    # Get user's completed jobs grouped by date
    completed_jobs = Job.objects.filter(status=JobStatus.COMPLETED).order_by("-created_at")

    # Group jobs by date
    jobs_by_date = {}
    for job in completed_jobs:
        date_key = job.created_at.strftime("%Y-%m-%d")
        if date_key not in jobs_by_date:
            jobs_by_date[date_key] = []
        jobs_by_date[date_key].append(job)

    # Get user's setting profiles
    from accounts.models import SettingProfile

    profiles = SettingProfile.objects.filter(user=request.user).order_by("name")
    default_profile = profiles.filter(is_default=True).first()

    return render(
        request,
        "index.html",
        {
            "jobs": jobs,
            "jobs_by_date": jobs_by_date,
            "user": request.user,
            "profiles": profiles,
            "default_profile": default_profile,
        },
    )


@login_required
@async_to_sync
async def serve_file(request, job_id: int, artifact_id: int):
    """Serve generated files from storage (local or S3)."""
    artifact = await Artifact.objects.filter(
        id=artifact_id,
        job__id=job_id,
    ).afirst()
    if not artifact:
        raise Http404("File not found")

    storage = get_storage()
    if artifact.artifact_type == ArtifactType.MERMAID_MINDMAP:
        mermaid_code = await storage.download_bytes(artifact.file_path)
        if mermaid_code is None:
            raise Http404("File not found")
        return render(
            request,
            "mindmap.html",
            {
                "mermaid_code": mermaid_code,
                "title": artifact.file_name,
            },
        )
    else:
        url = await storage.get_download_url(artifact.file_path, filename=artifact.file_name)
        if is_s3_enabled():
            return HttpResponseRedirect(url)
        else:
            return FileResponse(
                open(url, "rb"),
                as_attachment=True,
                filename=os.path.basename(artifact.file_name),
            )