"""
User model for Handout Generator.

Custom user model with OAuth integration for Authentik.
"""

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone

# Default column configuration for Excel spreadsheet
DEFAULT_SPREADSHEET_COLUMNS = [
    {"name": "Condition", "description": "The name of the disease or condition"},
    {"name": "Risk Factors", "description": "Risk factors for developing the condition"},
    {"name": "Etiology", "description": "The cause or origin of the condition"},
    {
        "name": "Pathology",
        "description": "The structural and functional changes caused by the disease",
    },
    {"name": "Pathophysiology", "description": "The mechanisms and progression of the disease"},
    {"name": "Clinical Presentation", "description": "Signs and symptoms patients present with"},
    {"name": "Diagnosis / Key Findings", "description": "Diagnostic criteria and key findings"},
    {"name": "Histology Key Findings", "description": "Microscopic findings on tissue examination"},
    {"name": "Prognosis", "description": "Expected outcome and disease progression"},
    {"name": "Treatment", "description": "Treatment options and management"},
    {
        "name": "Classic Step 1–Style Question Stem",
        "description": "A clinically plausible USMLE-style question stem",
    },
    {
        "name": "Photos from Lecture",
        "description": "Description of relevant images from the lecture",
    },
    {
        "name": "Additional Notes/Important Things",
        "description": "Additional notes and important points",
    },
    {"name": "Mnemonic", "description": "Memory aids for the condition"},
]


class UserManager(BaseUserManager):
    """Manager for custom User model."""

    def create_user(self, email, oauth_id=None, name=None, password=None, **extra_fields):
        """Create and return a regular user."""
        if not email:
            raise ValueError("Users must have an email address")

        email = self.normalize_email(email)
        user = self.model(
            email=email,
            oauth_id=oauth_id or "",
            name=name or email.split("@")[0],
            **extra_fields,
        )
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and return a superuser."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_admin", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model with OAuth support."""

    email = models.EmailField(unique=True, max_length=255)
    oauth_id = models.CharField(max_length=255, blank=True, default="")
    name = models.CharField(max_length=255)
    is_admin = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        db_table = "users"
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self):
        return f"{self.name} <{self.email}>"

    def get_short_name(self):
        """Return the short name for the user."""
        return self.name.split()[0] if self.name else self.email.split("@")[0]

    def get_full_name(self):
        """Return the full name for the user."""
        return self.name


class UserSettings(models.Model):
    """User-specific settings for handout generation."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="settings",
        primary_key=True,
    )

    # Custom prompts
    vignette_prompt = models.TextField(
        blank=True,
        null=True,
        help_text="Custom prompt for generating quiz/vignette questions. Leave blank to use default.",
    )
    spreadsheet_prompt = models.TextField(
        blank=True,
        null=True,
        help_text="Custom prompt for generating Excel study table. Leave blank to use default.",
    )

    # Excel column configuration (stored as JSON)
    spreadsheet_columns = models.JSONField(
        default=list,
        blank=True,
        help_text="Custom columns for Excel file. Each column should have 'name' and 'description' keys.",
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_settings"
        verbose_name = "user settings"
        verbose_name_plural = "user settings"

    def __str__(self):
        return f"Settings for {self.user.email}"

    def save(self, *args, **kwargs):
        # Set default columns if empty
        if not self.spreadsheet_columns:
            self.spreadsheet_columns = DEFAULT_SPREADSHEET_COLUMNS
        super().save(*args, **kwargs)

    def get_vignette_prompt(self) -> str | None:
        """Get the vignette prompt, or None if using default."""
        return self.vignette_prompt if self.vignette_prompt else None

    def get_spreadsheet_prompt(self) -> str | None:
        """Get the spreadsheet prompt, or None if using default."""
        return self.spreadsheet_prompt if self.spreadsheet_prompt else None

    def get_spreadsheet_columns(self) -> list[dict]:
        """Get the spreadsheet columns configuration."""
        if self.spreadsheet_columns:
            return self.spreadsheet_columns
        return DEFAULT_SPREADSHEET_COLUMNS
