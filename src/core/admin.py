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
        "enable_excel",
        "enable_vignette",
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "input_type", "enable_excel", "enable_vignette", "created_at")
    search_fields = ("label", "user__email", "taskiq_task_id")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "started_at", "completed_at", "taskiq_task_id")
    raw_id_fields = ("user",)

    fieldsets = (
        (
            None,
            {"fields": ("user", "label", "status", "progress", "current_stage", "error_message")},
        ),
        ("Input", {"fields": ("input_type", "input_data")}),
        (
            "Output Options",
            {
                "fields": ("enable_excel", "enable_vignette"),
                "description": "Control which outputs are generated for this job.",
            },
        ),
        ("Task Info", {"fields": ("taskiq_task_id",)}),
        ("Timestamps", {"fields": ("created_at", "started_at", "completed_at")}),
    )


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
