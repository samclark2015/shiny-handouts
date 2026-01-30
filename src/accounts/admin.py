"""Admin configuration for accounts app."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, UserSettings


class UserSettingsInline(admin.StackedInline):
    """Inline admin for UserSettings."""

    model = UserSettings
    can_delete = False
    verbose_name = "Settings"
    verbose_name_plural = "Settings"
    fieldsets = (
        (
            "Vignette/Quiz Settings",
            {
                "fields": ("vignette_prompt",),
                "description": "Custom prompt for generating USMLE-style vignette questions.",
            },
        ),
        (
            "Spreadsheet Settings",
            {
                "fields": ("spreadsheet_prompt", "spreadsheet_columns"),
                "description": "Custom prompt and columns for Excel study table generation.",
            },
        ),
    )


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for custom User model."""

    list_display = ("email", "name", "is_admin", "is_staff", "created_at", "last_login")
    list_filter = ("is_admin", "is_staff", "is_active", "created_at")
    search_fields = ("email", "name", "oauth_id")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "last_login", "oauth_id")
    inlines = [UserSettingsInline]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("name", "oauth_id")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_admin",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "created_at")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "name", "password1", "password2"),
            },
        ),
    )


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    """Admin configuration for UserSettings model."""

    list_display = ("user", "updated_at", "has_custom_vignette", "has_custom_spreadsheet")
    list_filter = ("updated_at",)
    search_fields = ("user__email", "user__name")
    ordering = ("-updated_at",)
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("user",)

    fieldsets = (
        (None, {"fields": ("user",)}),
        (
            "Vignette/Quiz Settings",
            {
                "fields": ("vignette_prompt",),
                "description": "Custom prompt for generating USMLE-style vignette questions.",
            },
        ),
        (
            "Spreadsheet Settings",
            {
                "fields": ("spreadsheet_prompt", "spreadsheet_columns"),
                "description": "Custom prompt and columns for Excel study table generation.",
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def has_custom_vignette(self, obj):
        """Check if user has custom vignette prompt."""
        return bool(obj.vignette_prompt)

    has_custom_vignette.boolean = True
    has_custom_vignette.short_description = "Custom Vignette"

    def has_custom_spreadsheet(self, obj):
        """Check if user has custom spreadsheet prompt."""
        return bool(obj.spreadsheet_prompt)

    has_custom_spreadsheet.boolean = True
    has_custom_spreadsheet.short_description = "Custom Spreadsheet"
