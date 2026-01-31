"""API views for HTMX interactions."""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Generator
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.text import get_valid_filename
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core.models import Job, JobStatus, Lecture


@require_POST
@login_required
def upload_file(request):
    """Handle file upload and start processing."""
    if "file" not in request.FILES:
        return render(request, "partials/error.html", {"message": "No file provided"}, status=400)

    file = request.FILES["file"]
    if file.name == "":
        return render(request, "partials/error.html", {"message": "No file selected"}, status=400)

    # Get per-job settings from form
    enable_excel = request.POST.get("enable_excel", "on") == "on"
    enable_vignette = request.POST.get("enable_vignette", "on") == "on"

    # Save the file
    filename = get_valid_filename(file.name)
    file_path = os.path.join(settings.INPUT_DIR, filename)
    
    os.makedirs(settings.INPUT_DIR, exist_ok=True)
    
    with open(file_path, "wb+") as destination:
        for chunk in file.chunks():
            destination.write(chunk)

    # Create job record
    job = Job.objects.create(
        user=request.user,
        label=filename,
        status=JobStatus.PENDING,
        input_type="upload",
        input_data=json.dumps({"path": file_path, "filename": filename}),
        enable_excel=enable_excel,
        enable_vignette=enable_vignette,
    )

    # Start the pipeline asynchronously
    from core.tasks import start_pipeline
    
    task_id = asyncio.run(start_pipeline(job.id, "upload", job.input_data))
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

    # Extract filename from URL
    filename = video_url.split("/")[-1].split("?")[0] or "video"

    # Create job record
    job = Job.objects.create(
        user=request.user,
        label=filename,
        status=JobStatus.PENDING,
        input_type="url",
        input_data=json.dumps({"url": video_url}),
        enable_excel=enable_excel,
        enable_vignette=enable_vignette,
    )

    # Start the pipeline
    from core.tasks import start_pipeline
    
    task_id = asyncio.run(start_pipeline(job.id, "url", job.input_data))
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

    # Parse Panopto URL
    parts = urlparse(panopto_url)
    qs = parse_qs(parts.query)
    delivery_id = qs.get("id", [""])[0]
    base = f"{parts.scheme}://{parts.netloc}"

    if not delivery_id:
        return render(
            request, "partials/error.html", {"message": "Invalid Panopto URL"}, status=400
        )

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
    )

    # Start the pipeline
    from core.tasks import start_pipeline
    
    task_id = asyncio.run(start_pipeline(job.id, "panopto", job.input_data))
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
        lectures = Lecture.objects.filter(user=request.user).order_by("-date")
        lectures_by_date = {}
        for lecture in lectures:
            date_key = lecture.date.strftime("%Y-%m-%d")
            if date_key not in lectures_by_date:
                lectures_by_date[date_key] = []
            lectures_by_date[date_key].append(lecture)
        
        file_browser = render(
            request,
            "partials/file_browser.html",
            {"lectures_by_date": lectures_by_date, "oob": True},
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
        
        task_id = asyncio.run(start_pipeline(job.id, job.input_type, job.input_data))
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
    lectures = Lecture.objects.filter(user=request.user).order_by("-date")

    # Group lectures by date
    lectures_by_date = {}
    for lecture in lectures:
        date_key = lecture.date.strftime("%Y-%m-%d")
        if date_key not in lectures_by_date:
            lectures_by_date[date_key] = []
        lectures_by_date[date_key].append(lecture)

    return render(request, "partials/file_browser.html", {"lectures_by_date": lectures_by_date})


@require_GET
@login_required
def get_lecture_artifacts(request, lecture_id: int):
    """Get artifacts for a specific lecture."""
    lecture = get_object_or_404(Lecture, id=lecture_id, user=request.user)
    return render(request, "partials/artifact_list.html", {"lecture": lecture})


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
                "id": job.id,
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
