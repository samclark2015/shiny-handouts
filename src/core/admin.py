"""Admin configuration for core app."""

from django.contrib import admin

from .models import Artifact, Job, Lecture


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    """Admin configuration for Job model."""

    list_display = (
        "id",
        "label",
        "user",
        "status",
        "progress",
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "input_type", "created_at")
    search_fields = ("label", "user__email", "taskiq_task_id")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "started_at", "completed_at", "taskiq_task_id")
    raw_id_fields = ("user",)


@admin.register(Lecture)
class LectureAdmin(admin.ModelAdmin):
    """Admin configuration for Lecture model."""

    list_display = ("id", "title", "user", "date", "created_at")
    list_filter = ("date", "created_at")
    search_fields = ("title", "user__email", "source_id")
    ordering = ("-date",)
    readonly_fields = ("created_at",)
    raw_id_fields = ("user", "job")


@admin.register(Artifact)
class ArtifactAdmin(admin.ModelAdmin):
    """Admin configuration for Artifact model."""

    list_display = (
        "id",
        "file_name",
        "artifact_type",
        "lecture",
        "file_size",
        "created_at",
    )
    list_filter = ("artifact_type", "created_at")
    search_fields = ("file_name", "lecture__title")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    raw_id_fields = ("lecture",)
