"""API views for HTMX interactions."""

import base64
import json
import os
import time
from collections.abc import Generator
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import jwt
import requests
from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.text import get_valid_filename
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core.models import Job, JobStatus

APP_ID = os.getenv("GITHUB_APP_ID", "")
INSTALLATION_ID = os.getenv("GITHUB_INSTALLATION_ID", "")
PRIVATE_KEY = base64.b64decode(os.getenv("GITHUB_PRIVATE_KEY", "")).decode("utf-8")
REPO = os.getenv("REPO", "")


@require_POST
@login_required
def upload_file(request):
    """Handle file upload and start processing."""
    from core.storage import is_s3_enabled, sync_upload_file

    if "file" not in request.FILES:
        return render(request, "partials/error.html", {"message": "No file provided"}, status=400)

    file = request.FILES["file"]
    if file.name == "":
        return render(request, "partials/error.html", {"message": "No file selected"}, status=400)

    # Get per-job settings from form
    enable_excel = request.POST.get("enable_excel", "on") == "on"
    enable_vignette = request.POST.get("enable_vignette", "on") == "on"
    profile_id = request.POST.get("profile_id", "").strip()

    # Save the file locally first
    filename = get_valid_filename(file.name)
    local_path = os.path.join(settings.INPUT_DIR, filename)

    os.makedirs(settings.INPUT_DIR, exist_ok=True)

    with open(local_path, "wb+") as destination:
        for chunk in file.chunks():
            destination.write(chunk)

    # Upload to S3 if enabled, otherwise use local path
    if is_s3_enabled():
        storage_path = sync_upload_file(local_path, "input", filename)
    else:
        storage_path = local_path

    # Get setting profile if specified
    from accounts.models import SettingProfile

    setting_profile = None
    if profile_id:
        try:
            setting_profile = SettingProfile.objects.get(id=int(profile_id), user=request.user)
        except (ValueError, SettingProfile.DoesNotExist):
            pass

    # Create job record
    job = Job.objects.create(
        user=request.user,
        label=filename,
        status=JobStatus.PENDING,
        input_type="upload",
        input_data=json.dumps({"path": storage_path, "filename": filename}),
        enable_excel=enable_excel,
        enable_vignette=enable_vignette,
        setting_profile=setting_profile,
    )

    # Start the pipeline asynchronously
    from core.tasks import start_pipeline

    task_id = async_to_sync(start_pipeline)(job.pk, "upload", job.input_data)
    job.taskiq_task_id = task_id
    job.save(update_fields=["taskiq_task_id"])

    return render(request, "partials/job_card.html", {"job": job, "animate": True})


@require_POST
@login_required
def process_url(request):
    """Handle URL submission and start processing."""
    video_url = request.POST.get("url", "").strip()

    if not video_url:
        return render(request, "partials/error.html", {"message": "No URL provided"}, status=400)

    # Get per-job settings from form
    enable_excel = request.POST.get("enable_excel", "on") == "on"
    enable_vignette = request.POST.get("enable_vignette", "on") == "on"
    profile_id = request.POST.get("profile_id", "").strip()

    # Extract filename from URL
    filename = video_url.split("/")[-1].split("?")[0] or "video"

    # Get setting profile if specified
    from accounts.models import SettingProfile

    setting_profile = None
    if profile_id:
        try:
            setting_profile = SettingProfile.objects.get(id=int(profile_id), user=request.user)
        except (ValueError, SettingProfile.DoesNotExist):
            pass

    # Create job record
    job = Job.objects.create(
        user=request.user,
        label=filename,
        status=JobStatus.PENDING,
        input_type="url",
        input_data=json.dumps({"url": video_url}),
        enable_excel=enable_excel,
        enable_vignette=enable_vignette,
        setting_profile=setting_profile,
    )

    # Start the pipeline
    from core.tasks import start_pipeline

    task_id = async_to_sync(start_pipeline)(job.pk, "url", job.input_data)
    job.taskiq_task_id = task_id
    job.save(update_fields=["taskiq_task_id"])

    return render(request, "partials/job_card.html", {"job": job, "animate": True})


@require_POST
@login_required
def process_panopto(request):
    """Handle Panopto submission and start processing."""
    panopto_url = request.POST.get("url", "").strip()
    cookie = request.POST.get("cookie", "").strip()

    if not panopto_url or not cookie:
        return render(
            request, "partials/error.html", {"message": "URL and cookie required"}, status=400
        )

    # Get per-job settings from form
    enable_excel = request.POST.get("enable_excel", "on") == "on"
    enable_vignette = request.POST.get("enable_vignette", "on") == "on"
    profile_id = request.POST.get("profile_id", "").strip()

    # Parse Panopto URL
    parts = urlparse(panopto_url)
    qs = parse_qs(parts.query)
    delivery_id = qs.get("id", [""])[0]
    base = f"{parts.scheme}://{parts.netloc}"

    if not delivery_id:
        return render(
            request, "partials/error.html", {"message": "Invalid Panopto URL"}, status=400
        )

    # Get setting profile if specified
    from accounts.models import SettingProfile

    setting_profile = None
    if profile_id:
        try:
            setting_profile = SettingProfile.objects.get(id=int(profile_id), user=request.user)
        except (ValueError, SettingProfile.DoesNotExist):
            pass

    # Create job record
    job = Job.objects.create(
        user=request.user,
        label=f"Panopto Video ({delivery_id[:8]}...)",
        status=JobStatus.PENDING,
        input_type="panopto",
        input_data=json.dumps(
            {
                "base": base,
                "cookie": cookie,
                "delivery_id": delivery_id,
            }
        ),
        enable_excel=enable_excel,
        enable_vignette=enable_vignette,
        setting_profile=setting_profile,
    )

    # Start the pipeline
    from core.tasks import start_pipeline

    task_id = async_to_sync(start_pipeline)(job.pk, "panopto", job.input_data)
    job.taskiq_task_id = task_id
    job.save(update_fields=["taskiq_task_id"])

    return render(request, "partials/job_card.html", {"job": job, "animate": True})


@require_GET
@login_required
def get_job(request, job_id: int):
    """Get job status for HTMX polling."""
    job = get_object_or_404(Job, id=job_id, user=request.user)

    response_html = render(request, "partials/job_card.html", {"job": job}).content.decode()

    # If job just completed, also refresh the file browser via OOB swap
    if job.status == JobStatus.COMPLETED:
        completed_jobs = Job.objects.filter(user=request.user, status=JobStatus.COMPLETED).order_by(
            "-created_at"
        )

        jobs_by_date = {}
        for completed_job in completed_jobs:
            date_key = completed_job.created_at.strftime("%Y-%m-%d")
            if date_key not in jobs_by_date:
                jobs_by_date[date_key] = []
            jobs_by_date[date_key].append(completed_job)

        file_browser = render(
            request,
            "partials/file_browser.html",
            {"jobs_by_date": jobs_by_date, "oob": True},
        ).content.decode()
        response_html += file_browser

    return HttpResponse(response_html)


@require_http_methods(["DELETE"])
@login_required
def cancel_job(request, job_id: int):
    """Cancel a running job."""
    job = get_object_or_404(Job, id=job_id, user=request.user)

    if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
        # Mark job as cancelling - tasks will check this, delete the job, and stop
        job.status = JobStatus.CANCELLING
        job.current_stage = "Cancelling..."
        job.save(update_fields=["status", "current_stage"])

    return render(request, "partials/job_card.html", {"job": job})


@require_POST
@login_required
def retry_job(request, job_id: int):
    """Retry a failed job."""
    job = get_object_or_404(Job, id=job_id, user=request.user)

    if job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
        # Reset job status
        job.status = JobStatus.PENDING
        job.progress = 0.0
        job.current_stage = None
        job.error_message = None
        job.started_at = None
        job.completed_at = None
        job.save()

        # Start new pipeline
        from core.tasks import start_pipeline

        task_id = async_to_sync(start_pipeline)(job.pk, job.input_type, job.input_data)
        job.taskiq_task_id = task_id
        job.save(update_fields=["taskiq_task_id"])

    return render(request, "partials/job_card.html", {"job": job})


@require_GET
@login_required
def get_jobs(request):
    """Get active jobs for the current user."""
    jobs = (
        Job.objects.filter(user=request.user)
        .filter(status__in=[JobStatus.PENDING, JobStatus.RUNNING])
        .order_by("-created_at")[:50]
    )
    return render(request, "partials/job_list.html", {"jobs": jobs})


@require_GET
@login_required
def get_files(request):
    """Get file browser for HTMX."""
    completed_jobs = Job.objects.filter(user=request.user, status=JobStatus.COMPLETED).order_by(
        "-created_at"
    )

    # Group jobs by date
    jobs_by_date = {}
    for job in completed_jobs:
        date_key = job.created_at.strftime("%Y-%m-%d")
        if date_key not in jobs_by_date:
            jobs_by_date[date_key] = []
        jobs_by_date[date_key].append(job)

    return render(request, "partials/file_browser.html", {"jobs_by_date": jobs_by_date})


@require_GET
@login_required
def get_job_artifacts(request, job_id: int):
    """Get artifacts for a specific job."""
    job = get_object_or_404(Job, id=job_id, user=request.user)
    return render(request, "partials/artifact_list.html", {"job": job})


@require_POST
@login_required
def rename_job(request, job_id: int):
    """Rename a job's title."""
    job = get_object_or_404(Job, id=job_id, user=request.user)
    new_title = request.POST.get("title", "").strip()

    if not new_title:
        return HttpResponse("Title cannot be empty", status=400)

    job.title = new_title
    job.save(update_fields=["title"])

    return render(request, "partials/job_title.html", {"job": job})


@require_GET
@login_required
def job_progress(request, job_id: int):
    """SSE endpoint for real-time job progress updates via Redis pub/sub."""
    job = get_object_or_404(Job, id=job_id, user=request.user)

    def event_stream() -> Generator[str, None, None]:
        """Generate SSE events from Redis pub/sub."""
        import redis

        redis_client = redis.from_url(settings.REDIS_URL)
        pubsub = redis_client.pubsub()
        pubsub.subscribe(f"job:{job_id}:progress")

        try:
            # Send initial state
            initial_data = {
                "id": job.pk,
                "status": job.status,
                "progress": int(job.progress * 100),
                "stage": job.current_stage or "",
                "error": job.error_message or "",
            }
            yield f"data: {json.dumps(initial_data)}\n\n"

            # Check if already complete
            if job.is_terminal:
                return

            # Listen for updates
            for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    yield f"data: {json.dumps(data)}\n\n"

                    # Stop if job is complete
                    if data.get("status") in ("completed", "failed", "cancelled"):
                        break
        finally:
            pubsub.unsubscribe()
            pubsub.close()
            redis_client.close()

    return StreamingHttpResponse(
        event_stream(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def generate_jwt():
    """Generate a JWT for GitHub App authentication"""
    private_key = PRIVATE_KEY

    payload = {
        "iat": int(time.time()) - 60,  # issued at
        "exp": int(time.time()) + (10 * 60),  # 10 minute expiration
        "iss": APP_ID,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def get_installation_token():
    """Exchange the JWT for an installation access token"""
    jwt_token = generate_jwt()
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
    }
    url = f"https://api.github.com/app/installations/{INSTALLATION_ID}/access_tokens"
    res = requests.post(url, headers=headers)
    if res.status_code != 201:
        raise Exception("Failed to get installation token")
    return res.json()["token"]


def send_bug_report_to_github(
    user_info: dict,
    timestamp: datetime,
    title: str,
    description: str,
    job_ids: list[int] | None = None,
) -> dict:
    """
    Function to send bug reports to GitHub using the GitHub App.

    Args:
        user_info: Dictionary containing user information (email, name, id)
        timestamp: Date and time when the bug was reported
        description: User's description of the issue
        job_ids: List of currently running job IDs for context

    Returns:
        Dictionary with submission status and any relevant data
    """
    token = get_installation_token()
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }

    # Build issue body with optional job context
    body_parts = [description]
    if job_ids:
        body_parts.append(f"\n\n**Active Jobs:** {', '.join(f'#{job_id}' for job_id in job_ids)}")
    body_parts.append(f"\n\n**User ID:** {user_info['id']}")
    body_parts.append("\n\n_Reported via anonymous form_")

    payload = {
        "title": f"[Anonymous Bug] {title or 'No Title Provided'}",
        "body": "".join(body_parts),
    }
    res = requests.post(
        f"https://api.github.com/repos/{REPO}/issues", json=payload, headers=headers
    )

    if res.status_code not in (200, 201):
        raise Exception(res.text)

    return {
        "message": "Bug reported successfully",
        "issue_url": res.json()["html_url"],
        "success": True,
    }


@require_POST
@login_required
def submit_bug_report(request):
    """Handle bug report submissions from users."""
    # Check if GitHub App is configured
    if not all([APP_ID, INSTALLATION_ID, PRIVATE_KEY, REPO]):
        return render(
            request,
            "partials/bug_report_error.html",
            {"error": "Bug reporting is not configured"},
            status=503,
        )

    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()

    if not description:
        return render(
            request,
            "partials/bug_report_error.html",
            {"error": "Description is required"},
            status=400,
        )

    # Gather user info
    user_info = {
        "id": request.user.id,
        "email": request.user.email,
    }

    # Get currently running or recently failed jobs for context
    one_hour_ago = datetime.now() - timedelta(hours=1)

    # Get running/pending jobs (any time) and failed jobs from last hour
    active_jobs = (
        Job.objects.filter(user=request.user)
        .filter(
            models.Q(status__in=[JobStatus.PENDING, JobStatus.RUNNING])
            | models.Q(status=JobStatus.FAILED, created_at__gte=one_hour_ago)
        )
        .values_list("id", flat=True)
    )
    job_ids = list(active_jobs) if active_jobs else None

    # Current timestamp
    timestamp = datetime.now()

    # Call stub service
    try:
        result = send_bug_report_to_github(
            user_info=user_info,
            timestamp=timestamp,
            title=title,
            description=description,
            job_ids=job_ids,
        )

        return render(
            request,
            "partials/bug_report_success.html",
            {"message": result["message"], "issue_url": result.get("issue_url")},
        )
    except Exception as e:
        return render(request, "partials/bug_report_error.html", {"error": str(e)}, status=500)
        return render(request, "partials/bug_report_error.html", {"error": str(e)}, status=500)
