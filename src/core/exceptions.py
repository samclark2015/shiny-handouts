"""Custom exceptions for the Handout Generator application."""


class HandoutGeneratorError(Exception):
    """Base exception for all handout generator errors."""

    pass


class StorageError(HandoutGeneratorError):
    """Exception raised for storage-related errors (S3, filesystem)."""

    pass


class AIError(HandoutGeneratorError):
    """Exception raised for AI/LLM API errors (OpenAI, etc)."""

    pass


class PipelineError(HandoutGeneratorError):
    """Exception raised for pipeline orchestration errors."""

    pass


class ValidationError(HandoutGeneratorError):
    """Exception raised for input validation errors."""

    pass


class RateLimitError(HandoutGeneratorError):
    """Exception raised when rate limits are exceeded."""

    pass
