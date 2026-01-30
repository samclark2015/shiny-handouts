"""Admin URL patterns for the core app."""

from django.urls import path

from core.views import admin

app_name = "admin"

urlpatterns = [
    path("", admin.dashboard, name="dashboard"),
    # User management
    path("users/", admin.users, name="users"),
    path("users/<int:user_id>/", admin.user_detail, name="user_detail"),
    path("users/<int:user_id>/toggle-admin/", admin.toggle_admin, name="toggle_admin"),
    path("users/<int:user_id>/delete/", admin.delete_user, name="delete_user"),
    # Job management
    path("jobs/", admin.jobs, name="jobs"),
    path("jobs/<int:job_id>/", admin.job_detail, name="job_detail"),
    path("jobs/<int:job_id>/cancel/", admin.admin_cancel_job, name="cancel_job"),
    path("jobs/<int:job_id>/delete/", admin.delete_job, name="delete_job"),
    # Lecture management
    path("lectures/", admin.lectures, name="lectures"),
    path("lectures/<int:lecture_id>/", admin.lecture_detail, name="lecture_detail"),
    path(
        "lectures/<int:lecture_id>/delete/", admin.delete_lecture, name="delete_lecture"
    ),
    path(
        "lectures/<int:lecture_id>/rename/", admin.rename_lecture, name="rename_lecture"
    ),
    path(
        "artifacts/<int:artifact_id>/rename/",
        admin.rename_artifact,
        name="rename_artifact",
    ),
]
