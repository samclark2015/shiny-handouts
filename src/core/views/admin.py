"""Admin views for managing users, jobs, and lectures."""

import os
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.models import User
from core.models import Artifact, Job, JobStatus, Lecture


def admin_required(view_func):
    """Decorator to require admin access."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin:
            raise Http404("Not found")
        return view_func(request, *args, **kwargs)

    return wrapper


@require_GET
@admin_required
def dashboard(request):
    """Admin dashboard with system overview."""
    stats = {
        "total_users": User.objects.count(),
        "total_jobs": Job.objects.count(),
        "pending_jobs": Job.objects.filter(status=JobStatus.PENDING).count(),
        "running_jobs": Job.objects.filter(status=JobStatus.RUNNING).count(),
        "completed_jobs": Job.objects.filter(status=JobStatus.COMPLETED).count(),
        "failed_jobs": Job.objects.filter(status=JobStatus.FAILED).count(),
        "total_lectures": Lecture.objects.count(),
        "total_artifacts": Artifact.objects.count(),
    }

    recent_jobs = Job.objects.order_by("-created_at")[:10]
    recent_users = User.objects.order_by("-created_at")[:10]

    return render(
        request,
        "admin/dashboard.html",
        {
            "stats": stats,
            "recent_jobs": recent_jobs,
            "recent_users": recent_users,
        },
    )


@require_GET
@admin_required
def users(request):
    """List all users."""
    page = request.GET.get("page", 1)
    users_query = User.objects.order_by("-created_at")
    paginator = Paginator(users_query, 20)
    users_page = paginator.get_page(page)

    return render(
        request, "admin/users.html", {"users": users_page, "pagination": users_page}
    )


@require_GET
@admin_required
def user_detail(request, user_id: int):
    """View user details."""
    user = get_object_or_404(User, id=user_id)
    jobs = Job.objects.filter(user=user).order_by("-created_at")[:20]
    lectures = Lecture.objects.filter(user=user).order_by("-date")[:20]

    return render(
        request,
        "admin/user_detail.html",
        {"user": user, "jobs": jobs, "lectures": lectures},
    )


@require_POST
@admin_required
def toggle_admin(request, user_id: int):
    """Toggle admin status for a user."""
    user = get_object_or_404(User, id=user_id)

    # Prevent removing own admin status
    if user.id == request.user.id:
        messages.error(request, "Cannot change your own admin status.")
        return redirect("admin:user_detail", user_id=user_id)

    user.is_admin = not user.is_admin
    user.save(update_fields=["is_admin"])

    status = "granted" if user.is_admin else "revoked"
    messages.success(request, f"Admin status {status} for {user.email}")
    return redirect("admin:user_detail", user_id=user_id)


@require_POST
@admin_required
def delete_user(request, user_id: int):
    """Delete a user."""
    user = get_object_or_404(User, id=user_id)

    # Prevent deleting yourself
    if user.id == request.user.id:
        messages.error(request, "Cannot delete your own account.")
        return redirect("admin:user_detail", user_id=user_id)

    email = user.email
    user.delete()
    messages.success(request, f"User {email} deleted.")
    return redirect("admin:users")


@require_GET
@admin_required
def jobs(request):
    """List all jobs."""
    page = request.GET.get("page", 1)
    status_filter = request.GET.get("status")

    jobs_query = Job.objects.order_by("-created_at")
    if status_filter:
        jobs_query = jobs_query.filter(status=status_filter)

    paginator = Paginator(jobs_query, 20)
    jobs_page = paginator.get_page(page)

    return render(
        request,
        "admin/jobs.html",
        {
            "jobs": jobs_page,
            "pagination": jobs_page,
            "status_filter": status_filter,
            "statuses": JobStatus.choices,
        },
    )


@require_GET
@admin_required
def job_detail(request, job_id: int):
    """View job details."""
    job = get_object_or_404(Job, id=job_id)
    return render(request, "admin/job_detail.html", {"job": job})


@require_POST
@admin_required
def admin_cancel_job(request, job_id: int):
    """Cancel a job (admin)."""
    job = get_object_or_404(Job, id=job_id)

    if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
        job.status = JobStatus.CANCELLED
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at"])
        messages.success(request, f"Job {job_id} cancelled.")
    else:
        messages.warning(request, f"Job {job_id} is not running.")

    return redirect("admin:job_detail", job_id=job_id)


@require_POST
@admin_required
def delete_job(request, job_id: int):
    """Delete a job."""
    job = get_object_or_404(Job, id=job_id)
    job.delete()
    messages.success(request, f"Job {job_id} deleted.")
    return redirect("admin:jobs")


@require_GET
@admin_required
def lectures(request):
    """List all lectures."""
    page = request.GET.get("page", 1)
    lectures_query = Lecture.objects.order_by("-date")
    paginator = Paginator(lectures_query, 20)
    lectures_page = paginator.get_page(page)

    return render(
        request,
        "admin/lectures.html",
        {"lectures": lectures_page, "pagination": lectures_page},
    )


@require_GET
@admin_required
def lecture_detail(request, lecture_id: int):
    """View lecture details."""
    lecture = get_object_or_404(Lecture, id=lecture_id)
    return render(request, "admin/lecture_detail.html", {"lecture": lecture})


@require_POST
@admin_required
def delete_lecture(request, lecture_id: int):
    """Delete a lecture and its artifacts."""
    lecture = get_object_or_404(Lecture, id=lecture_id)

    # Delete artifact files
    for artifact in lecture.artifacts.all():
        if artifact.file_path and os.path.exists(artifact.file_path):
            try:
                os.remove(artifact.file_path)
            except OSError:
                pass

    lecture.delete()
    messages.success(request, f"Lecture '{lecture.title}' deleted.")
    return redirect("admin:lectures")


@require_POST
@admin_required
def rename_lecture(request, lecture_id: int):
    """Rename a lecture."""
    lecture = get_object_or_404(Lecture, id=lecture_id)
    new_title = request.POST.get("title", "").strip()

    if new_title:
        lecture.title = new_title
        lecture.save(update_fields=["title"])
        messages.success(request, f"Lecture renamed to '{new_title}'.")
    else:
        messages.error(request, "Title cannot be empty.")

    return redirect("admin:lecture_detail", lecture_id=lecture_id)


@require_POST
@admin_required
def rename_artifact(request, artifact_id: int):
    """Rename an artifact file."""
    artifact = get_object_or_404(Artifact, id=artifact_id)
    new_name = request.POST.get("name", "").strip()

    if new_name:
        # Rename the file on disk if it exists
        if artifact.file_path and os.path.exists(artifact.file_path):
            old_path = artifact.file_path
            new_path = os.path.join(os.path.dirname(old_path), new_name)
            try:
                os.rename(old_path, new_path)
                artifact.file_path = new_path
                artifact.file_name = new_name
                artifact.save(update_fields=["file_path", "file_name"])
                messages.success(request, f"Artifact renamed to '{new_name}'.")
            except OSError as e:
                messages.error(request, f"Failed to rename file: {e}")
        else:
            artifact.file_name = new_name
            artifact.save(update_fields=["file_name"])
            messages.success(request, f"Artifact renamed to '{new_name}'.")
    else:
        messages.error(request, "Name cannot be empty.")

    return redirect("admin:lecture_detail", lecture_id=artifact.lecture_id)
