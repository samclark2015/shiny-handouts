"""API URL patterns for HTMX interactions."""

from django.urls import path

from core.views import api

app_name = "api"

urlpatterns = [
    # File upload and URL processing
    path("upload", api.upload_file, name="upload_file"),
    path("url", api.process_url, name="process_url"),
    path("panopto", api.process_panopto, name="process_panopto"),
    # Job management
    path("jobs", api.get_jobs, name="get_jobs"),
    path("jobs/<int:job_id>", api.get_job, name="get_job"),
    path("jobs/<int:job_id>/cancel", api.cancel_job, name="cancel_job"),
    path("jobs/<int:job_id>/retry", api.retry_job, name="retry_job"),
    path("jobs/<int:job_id>/progress", api.job_progress, name="job_progress"),
    # File browser
    path("files", api.get_files, name="get_files"),
    path(
        "lectures/<int:lecture_id>/artifacts",
        api.get_lecture_artifacts,
        name="get_lecture_artifacts",
    ),
]
