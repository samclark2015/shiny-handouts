"""
Flask routes for Shiny Handouts.

Provides:
- Main page with file upload and task management
- API endpoints for HTMX interactions
- SSE endpoint for real-time progress updates
- OAuth authentication flow
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Generator
from urllib.parse import parse_qs, urlparse

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.utils import secure_filename

from models import Job, JobStatus, Lecture, User, db
from tasks import start_pipeline

# Blueprints
main_bp = Blueprint("main", __name__)
api_bp = Blueprint("api", __name__)
auth_bp = Blueprint("auth", __name__)


# Main Routes


@main_bp.route("/")
@login_required
def index():
    """Main page with file upload and task list."""
    # Get user's jobs
    jobs = (
        Job.query.filter_by(user_id=current_user.id)
        .order_by(Job.created_at.desc())
        .limit(50)
        .all()
    )

    # Get user's lectures grouped by date
    lectures = (
        Lecture.query.filter_by(user_id=current_user.id)
        .order_by(Lecture.date.desc())
        .all()
    )

    # Group lectures by date
    lectures_by_date = {}
    for lecture in lectures:
        date_key = lecture.date.strftime("%Y-%m-%d")
        if date_key not in lectures_by_date:
            lectures_by_date[date_key] = []
        lectures_by_date[date_key].append(lecture)

    return render_template(
        "index.html",
        jobs=jobs,
        lectures_by_date=lectures_by_date,
        user=current_user,
    )


@main_bp.route("/files/<path:filename>")
@login_required
def serve_file(filename: str):
    """Serve generated files."""
    output_folder = current_app.config["OUTPUT_FOLDER"]
    return send_from_directory(output_folder, filename)


# API Routes for HTMX


@api_bp.route("/upload", methods=["POST"])
@login_required
def upload_file():
    """Handle file upload and start processing."""
    if "file" not in request.files:
        return render_template("partials/error.html", message="No file provided"), 400

    file = request.files["file"]
    if file.filename == "":
        return render_template("partials/error.html", message="No file selected"), 400

    # Save the file
    filename = secure_filename(file.filename)
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)

    # Create job record
    job = Job(
        user_id=current_user.id,
        label=filename,
        status=JobStatus.PENDING,
        input_type="upload",
        input_data=json.dumps({"path": file_path, "filename": filename}),
    )
    db.session.add(job)
    db.session.commit()

    # Start the pipeline
    task_id = start_pipeline(job.id, "upload", job.input_data)
    job.celery_task_id = task_id
    db.session.commit()

    return render_template("partials/job_card.html", job=job, animate=True)


@api_bp.route("/url", methods=["POST"])
@login_required
def process_url():
    """Handle URL submission and start processing."""
    video_url = request.form.get("url", "").strip()

    if not video_url:
        return render_template("partials/error.html", message="No URL provided"), 400

    # Extract filename from URL
    filename = video_url.split("/")[-1].split("?")[0] or "video"

    # Create job record
    job = Job(
        user_id=current_user.id,
        label=filename,
        status=JobStatus.PENDING,
        input_type="url",
        input_data=json.dumps({"url": video_url}),
    )
    db.session.add(job)
    db.session.commit()

    # Start the pipeline
    task_id = start_pipeline(job.id, "url", job.input_data)
    job.celery_task_id = task_id
    db.session.commit()

    return render_template("partials/job_card.html", job=job, animate=True)


@api_bp.route("/panopto", methods=["POST"])
@login_required
def process_panopto():
    """Handle Panopto submission and start processing."""
    panopto_url = request.form.get("url", "").strip()
    cookie = request.form.get("cookie", "").strip()

    if not panopto_url or not cookie:
        return render_template(
            "partials/error.html", message="URL and cookie required"
        ), 400

    # Parse Panopto URL
    parts = urlparse(panopto_url)
    qs = parse_qs(parts.query)
    delivery_id = qs.get("id", [""])[0]
    base = f"{parts.scheme}://{parts.netloc}"

    if not delivery_id:
        return render_template(
            "partials/error.html", message="Invalid Panopto URL"
        ), 400

    # Create job record
    job = Job(
        user_id=current_user.id,
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
    )
    db.session.add(job)
    db.session.commit()

    # Start the pipeline
    task_id = start_pipeline(job.id, "panopto", job.input_data)
    job.celery_task_id = task_id
    db.session.commit()

    return render_template("partials/job_card.html", job=job, animate=True)


@api_bp.route("/jobs/<int:job_id>")
@login_required
def get_job(job_id: int):
    """Get job status for HTMX polling."""
    job = db.session.get(Job, job_id)

    if not job or job.user_id != current_user.id:
        return "", 404

    return render_template("partials/job_card.html", job=job)


@api_bp.route("/jobs/<int:job_id>/cancel", methods=["DELETE"])
@login_required
def cancel_job(job_id: int):
    """Cancel a running job."""
    from celery_app import celery_app

    job = db.session.get(Job, job_id)

    if not job or job.user_id != current_user.id:
        return "", 404

    if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
        if job.celery_task_id:
            celery_app.control.revoke(job.celery_task_id, terminate=True)

        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc)
        db.session.commit()

    return render_template("partials/job_card.html", job=job)


@api_bp.route("/jobs/<int:job_id>/retry", methods=["POST"])
@login_required
def retry_job(job_id: int):
    """Retry a failed job."""
    job = db.session.get(Job, job_id)

    if not job or job.user_id != current_user.id:
        return "", 404

    if job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
        # Reset job status
        job.status = JobStatus.PENDING
        job.progress = 0.0
        job.current_stage = None
        job.error_message = None
        job.started_at = None
        job.completed_at = None
        db.session.commit()

        # Start new pipeline
        task_id = start_pipeline(job.id, job.input_type, job.input_data)
        job.celery_task_id = task_id
        db.session.commit()

    return render_template("partials/job_card.html", job=job)


@api_bp.route("/jobs")
@login_required
def get_jobs():
    """Get all jobs for the current user."""
    jobs = (
        Job.query.filter_by(user_id=current_user.id)
        .order_by(Job.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template("partials/job_list.html", jobs=jobs)


@api_bp.route("/files")
@login_required
def get_files():
    """Get file browser for HTMX."""
    lectures = (
        Lecture.query.filter_by(user_id=current_user.id)
        .order_by(Lecture.date.desc())
        .all()
    )

    # Group lectures by date
    lectures_by_date = {}
    for lecture in lectures:
        date_key = lecture.date.strftime("%Y-%m-%d")
        if date_key not in lectures_by_date:
            lectures_by_date[date_key] = []
        lectures_by_date[date_key].append(lecture)

    return render_template(
        "partials/file_browser.html", lectures_by_date=lectures_by_date
    )


@api_bp.route("/lectures/<int:lecture_id>/artifacts")
@login_required
def get_lecture_artifacts(lecture_id: int):
    """Get artifacts for a specific lecture."""
    lecture = db.session.get(Lecture, lecture_id)

    if not lecture or lecture.user_id != current_user.id:
        return "", 404

    return render_template("partials/artifact_list.html", lecture=lecture)


# SSE Progress Endpoint


@api_bp.route("/jobs/<int:job_id>/progress")
@login_required
def job_progress(job_id: int):
    """SSE endpoint for real-time job progress updates."""
    job = db.session.get(Job, job_id)

    if not job or job.user_id != current_user.id:
        return "", 404

    def generate() -> Generator[str, None, None]:
        """Generate SSE events for job progress."""
        last_progress = -1
        last_status = None

        while True:
            # Refresh job from database
            db.session.refresh(job)

            # Send update if changed
            if job.progress != last_progress or job.status != last_status:
                last_progress = job.progress
                last_status = job.status

                data = {
                    "id": job.id,
                    "status": job.status.value,
                    "progress": int(job.progress * 100),
                    "stage": job.current_stage or "",
                    "error": job.error_message or "",
                }

                yield f"data: {json.dumps(data)}\n\n"

                # Stop streaming if job is complete
                if job.status in (
                    JobStatus.COMPLETED,
                    JobStatus.FAILED,
                    JobStatus.CANCELLED,
                ):
                    break

            time.sleep(1)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# Auth Routes (Flask-Dance OAuth)


@auth_bp.route("/login")
def login():
    """Login page."""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    return render_template("login.html")


@auth_bp.route("/login/start")
def oauth_login():
    """Start OAuth flow."""
    from authlib.integrations.flask_client import OAuth

    oauth = OAuth(current_app)
    oauth_url = os.environ.get("OAUTH_URL", "")
    client_id = os.environ.get("OAUTH_CLIENT_ID", "")
    client_secret = os.environ.get("OAUTH_CLIENT_SECRET", "")

    oauth.register(
        "authentik",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=oauth_url,
        client_kwargs={"scope": "openid email profile"},
    )

    redirect_uri = url_for("auth.oauth_callback", _external=True)
    return oauth.authentik.authorize_redirect(redirect_uri)


@auth_bp.route("/callback")
def oauth_callback():
    """Handle OAuth callback."""
    from authlib.integrations.flask_client import OAuth

    oauth = OAuth(current_app)
    oauth_url = os.environ.get("OAUTH_URL", "")
    client_id = os.environ.get("OAUTH_CLIENT_ID", "")
    client_secret = os.environ.get("OAUTH_CLIENT_SECRET", "")

    oauth.register(
        "authentik",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=oauth_url,
        client_kwargs={"scope": "openid email profile"},
    )

    try:
        token = oauth.authentik.authorize_access_token()
    except Exception as e:
        flash(f"OAuth error: {e}", category="error")
        return redirect(url_for("auth.login"))

    user_info = token.get("userinfo", {})
    oauth_id = user_info.get("sub")
    email = user_info.get("email")
    name = user_info.get("name") or user_info.get("preferred_username") or email

    if not oauth_id or not email:
        flash("Invalid user information received.", category="error")
        return redirect(url_for("auth.login"))

    # Find or create user
    user = User.query.filter_by(oauth_id=oauth_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()
        if user:
            user.oauth_id = oauth_id
        else:
            user = User(
                oauth_id=oauth_id,
                email=email,
                name=name,
            )
            db.session.add(user)

    user.name = name
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    login_user(user)

    return redirect(url_for("main.index"))


@auth_bp.route("/logout")
@login_required
def logout():
    """Logout and redirect to login page."""
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))
