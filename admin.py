"""
Admin routes for Shiny Handouts.

Provides admin dashboard and management functionality for:
- Users
- Jobs
- Lectures
- System overview
"""

from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models import Artifact, Job, JobStatus, Lecture, User, db

admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    """Decorator to require admin access."""

    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


@admin_bp.route("/")
@admin_required
def dashboard():
    """Admin dashboard with system overview."""
    # Get statistics
    stats = {
        "total_users": User.query.count(),
        "total_jobs": Job.query.count(),
        "pending_jobs": Job.query.filter_by(status=JobStatus.PENDING).count(),
        "running_jobs": Job.query.filter_by(status=JobStatus.RUNNING).count(),
        "completed_jobs": Job.query.filter_by(status=JobStatus.COMPLETED).count(),
        "failed_jobs": Job.query.filter_by(status=JobStatus.FAILED).count(),
        "total_lectures": Lecture.query.count(),
        "total_artifacts": Artifact.query.count(),
    }

    # Recent jobs
    recent_jobs = Job.query.order_by(Job.created_at.desc()).limit(10).all()

    # Recent users
    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_jobs=recent_jobs,
        recent_users=recent_users,
    )


@admin_bp.route("/users")
@admin_required
def users():
    """List all users."""
    page = request.args.get("page", 1, type=int)
    per_page = 20

    users_query = User.query.order_by(User.created_at.desc())
    pagination = users_query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template("admin/users.html", users=pagination.items, pagination=pagination)


@admin_bp.route("/users/<int:user_id>")
@admin_required
def user_detail(user_id: int):
    """View user details."""
    user = db.session.get(User, user_id)
    if not user:
        abort(404)

    jobs = Job.query.filter_by(user_id=user_id).order_by(Job.created_at.desc()).limit(20).all()
    lectures = Lecture.query.filter_by(user_id=user_id).order_by(Lecture.date.desc()).limit(20).all()

    return render_template("admin/user_detail.html", user=user, jobs=jobs, lectures=lectures)


@admin_bp.route("/users/<int:user_id>/toggle-admin", methods=["POST"])
@admin_required
def toggle_admin(user_id: int):
    """Toggle admin status for a user."""
    user = db.session.get(User, user_id)
    if not user:
        abort(404)

    # Prevent removing own admin status
    if user.id == current_user.id:
        flash("You cannot change your own admin status.", "error")
        return redirect(url_for("admin.user_detail", user_id=user_id))

    user.is_admin = not user.is_admin
    db.session.commit()

    status = "granted" if user.is_admin else "revoked"
    flash(f"Admin access {status} for {user.name}.", "success")
    return redirect(url_for("admin.user_detail", user_id=user_id))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id: int):
    """Delete a user and all their data."""
    user = db.session.get(User, user_id)
    if not user:
        abort(404)

    # Prevent self-deletion
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("admin.user_detail", user_id=user_id))

    name = user.name
    db.session.delete(user)
    db.session.commit()

    flash(f"User {name} has been deleted.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/jobs")
@admin_required
def jobs():
    """List all jobs."""
    page = request.args.get("page", 1, type=int)
    per_page = 20
    status_filter = request.args.get("status")

    jobs_query = Job.query.order_by(Job.created_at.desc())

    if status_filter:
        try:
            status_enum = JobStatus(status_filter)
            jobs_query = jobs_query.filter_by(status=status_enum)
        except ValueError:
            pass

    pagination = jobs_query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        "admin/jobs.html",
        jobs=pagination.items,
        pagination=pagination,
        status_filter=status_filter,
        job_statuses=[s.value for s in JobStatus],
    )


@admin_bp.route("/jobs/<int:job_id>")
@admin_required
def job_detail(job_id: int):
    """View job details."""
    job = db.session.get(Job, job_id)
    if not job:
        abort(404)

    return render_template("admin/job_detail.html", job=job)


@admin_bp.route("/jobs/<int:job_id>/cancel", methods=["POST"])
@admin_required
def cancel_job(job_id: int):
    """Cancel a running job."""
    from celery_app import celery_app

    job = db.session.get(Job, job_id)
    if not job:
        abort(404)

    if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
        if job.celery_task_id:
            celery_app.control.revoke(job.celery_task_id, terminate=True)

        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        flash(f"Job {job_id} has been cancelled.", "success")

    return redirect(url_for("admin.job_detail", job_id=job_id))


@admin_bp.route("/jobs/<int:job_id>/delete", methods=["POST"])
@admin_required
def delete_job(job_id: int):
    """Delete a job."""
    job = db.session.get(Job, job_id)
    if not job:
        abort(404)

    db.session.delete(job)
    db.session.commit()

    flash(f"Job {job_id} has been deleted.", "success")
    return redirect(url_for("admin.jobs"))


@admin_bp.route("/lectures")
@admin_required
def lectures():
    """List all lectures."""
    page = request.args.get("page", 1, type=int)
    per_page = 20

    lectures_query = Lecture.query.order_by(Lecture.date.desc())
    pagination = lectures_query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template("admin/lectures.html", lectures=pagination.items, pagination=pagination)


@admin_bp.route("/lectures/<int:lecture_id>")
@admin_required
def lecture_detail(lecture_id: int):
    """View lecture details."""
    lecture = db.session.get(Lecture, lecture_id)
    if not lecture:
        abort(404)

    return render_template("admin/lecture_detail.html", lecture=lecture)


@admin_bp.route("/lectures/<int:lecture_id>/delete", methods=["POST"])
@admin_required
def delete_lecture(lecture_id: int):
    """Delete a lecture and its artifacts."""
    lecture = db.session.get(Lecture, lecture_id)
    if not lecture:
        abort(404)

    title = lecture.title
    db.session.delete(lecture)
    db.session.commit()

    flash(f"Lecture '{title}' has been deleted.", "success")
    return redirect(url_for("admin.lectures"))
