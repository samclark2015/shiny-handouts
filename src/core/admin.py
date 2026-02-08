"""Admin configuration for core app."""

from django.contrib import admin

from .models import AIRequest, Artifact, Job


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


@admin.register(AIRequest)
class AIRequestAdmin(admin.ModelAdmin):
    """Admin configuration for AI Request model."""

    list_display = (
        "id",
        "function_name",
        "model",
        "user",
        "job",
        "total_tokens",
        "estimated_cost_usd",
        "duration_ms",
        "cached",
        "success",
        "created_at",
    )
    list_filter = (
        "model",
        "function_name",
        "cached",
        "success",
        "created_at",
    )
    search_fields = (
        "function_name",
        "user__email",
        "job__label",
        "job__title",
    )
    ordering = ("-created_at",)
    readonly_fields = (
        "function_name",
        "model",
        "user",
        "job",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "estimated_cost_usd",
        "duration_ms",
        "cached",
        "success",
        "error_message",
        "created_at",
    )
    raw_id_fields = ("user", "job")

    fieldsets = (
        (
            "Request Info",
            {
                "fields": (
                    "function_name",
                    "model",
                    "cached",
                    "success",
                    "error_message",
                )
            },
        ),
        (
            "Relationships",
            {
                "fields": ("user", "job"),
            },
        ),
        (
            "Usage & Cost",
            {
                "fields": (
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "estimated_cost_usd",
                    "duration_ms",
                )
            },
        ),
        ("Timestamp", {"fields": ("created_at",)}),
    )

    def has_add_permission(self, request):
        """Disable manual creation of AI requests."""
        return False

    def has_change_permission(self, request, obj=None):
        """Make AI requests read-only."""
        return False
