"""Admin configuration for core app."""

from django.contrib import admin

from .models import Artifact, Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    """Admin configuration for Job model."""

    list_display = (
        "id",
        "label",
        "title",
        "user",
        "status",
        "progress",
        "enable_excel",
        "enable_vignette",
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "input_type", "enable_excel", "enable_vignette", "created_at")
    search_fields = ("label", "title", "user__email", "taskiq_task_id", "source_id")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "started_at", "completed_at", "taskiq_task_id", "source_id")
    raw_id_fields = ("user",)

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "user",
                    "label",
                    "title",
                    "status",
                    "progress",
                    "current_stage",
                    "error_message",
                )
            },
        ),
        ("Input", {"fields": ("input_type", "input_data")}),
        ("Source", {"fields": ("source_id", "video_path")}),
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


@admin.register(Artifact)
class ArtifactAdmin(admin.ModelAdmin):
    """Admin configuration for Artifact model."""

    list_display = (
        "id",
        "file_name",
        "artifact_type",
        "job",
        "file_size",
        "created_at",
    )
    list_filter = ("artifact_type", "created_at")
    search_fields = ("file_name", "job__title", "job__label")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    raw_id_fields = ("job",)
