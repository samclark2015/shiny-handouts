"""
TaskContext dataclass for pipeline state management.
"""

import os
from dataclasses import asdict, dataclass

from .config import IN_DIR


@dataclass
class TaskContext:
    """Context object that flows through the pipeline stages."""

    job_id: int
    source_id: str
    input_type: str  # 'url', 'upload', 'panopto'
    input_data: dict  # Serialized input configuration
    use_ai: bool = True
    video_path: str | None = None
    captions: list[dict] | None = None
    slides: list[dict] | None = None
    outputs: dict | None = None

    # Per-job settings
    enable_excel: bool = True
    enable_vignette: bool = True
    enable_mindmap: bool = True

    # User settings (custom prompts)
    vignette_prompt: str | None = None
    spreadsheet_prompt: str | None = None
    spreadsheet_columns: list[dict] | None = None
    mindmap_prompt: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TaskContext":
        return cls(**data)

    def update_from(self, other: "TaskContext") -> None:
        """Update this instance with non-None values from another instance."""
        for field in self.__dataclass_fields__:
            other_value = getattr(other, field)
            if other_value is not None:
                setattr(self, field, other_value)

    def get_video_path(self) -> str:
        """Get the path to the video file."""
        if self.video_path and os.path.exists(self.video_path):
            return self.video_path
        return os.path.join(IN_DIR, f"video_{self.source_id}.mp4")
