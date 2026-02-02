"""
S3 Storage utilities for file operations.

This module provides a unified interface for file storage operations that works
with both local filesystem and S3 storage, depending on configuration.
"""

import asyncio
import logging
import mimetypes
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Literal

import aioboto3
from django.conf import settings


@dataclass
class StorageConfig:
    """Configuration for storage backend."""

    use_s3: bool
    bucket_name: str
    region: str
    endpoint_url: str | None
    access_key_id: str
    secret_access_key: str
    input_prefix: str
    output_prefix: str
    frames_prefix: str
    skip_content_disposition: bool
    use_path_style: bool

    @classmethod
    def from_settings(cls) -> "StorageConfig":
        """Create storage config from Django settings."""
        return cls(
            use_s3=getattr(settings, "USE_S3_STORAGE", False),
            bucket_name=getattr(settings, "S3_BUCKET_NAME", ""),
            region=getattr(settings, "S3_REGION", "us-east-1"),
            endpoint_url=getattr(settings, "S3_ENDPOINT_URL", "") or None,
            access_key_id=getattr(settings, "S3_ACCESS_KEY_ID", ""),
            secret_access_key=getattr(settings, "S3_SECRET_ACCESS_KEY", ""),
            input_prefix=getattr(settings, "S3_INPUT_PREFIX", "input/"),
            output_prefix=getattr(settings, "S3_OUTPUT_PREFIX", "output/"),
            frames_prefix=getattr(settings, "S3_FRAMES_PREFIX", "frames/"),
            skip_content_disposition=getattr(settings, "S3_SKIP_CONTENT_DISPOSITION", False),
            use_path_style=getattr(settings, "S3_USE_PATH_STYLE", False),
        )


StorageType = Literal["input", "output", "frames"]


def get_storage_config() -> StorageConfig:
    """Get the current storage configuration."""
    return StorageConfig.from_settings()


def is_s3_enabled() -> bool:
    """Check if S3 storage is enabled."""
    config = get_storage_config()
    return config.use_s3 and bool(config.bucket_name)


# =============================================================================
# Abstract Storage Interface
# =============================================================================


class Storage(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def upload_file(
        self,
        local_path: str,
        storage_path: str,
        content_type: str | None = None,
    ) -> str:
        """Upload a file to storage.

        Args:
            local_path: Path to the local file to upload
            storage_path: Destination path in storage
            content_type: Optional MIME type

        Returns:
            The storage path
        """
        pass

    @abstractmethod
    async def upload_bytes(
        self,
        data: bytes,
        storage_path: str,
        content_type: str | None = None,
    ) -> str:
        """Upload bytes data to storage.

        Args:
            data: The bytes to upload
            storage_path: Destination path in storage
            content_type: Optional MIME type

        Returns:
            The storage path
        """
        pass

    @abstractmethod
    async def download_file(
        self,
        storage_path: str,
        local_path: str | None = None,
    ) -> str:
        """Download a file from storage to local filesystem.

        Args:
            storage_path: The storage path
            local_path: Optional destination local path

        Returns:
            The local file path
        """
        pass

    @abstractmethod
    async def download_bytes(self, storage_path: str) -> bytes:
        """Download a file from storage as bytes.

        Args:
            storage_path: The storage path

        Returns:
            The file contents as bytes
        """
        pass

    @abstractmethod
    async def file_exists(self, storage_path: str) -> bool:
        """Check if a file exists in storage.

        Args:
            storage_path: The storage path

        Returns:
            True if the file exists
        """
        pass

    @abstractmethod
    async def delete_file(self, storage_path: str) -> None:
        """Delete a file from storage.

        Args:
            storage_path: The storage path
        """
        pass

    @abstractmethod
    async def get_file_size(self, storage_path: str) -> int:
        """Get the size of a file in storage.

        Args:
            storage_path: The storage path

        Returns:
            File size in bytes
        """
        pass

    @abstractmethod
    async def get_download_url(
        self,
        storage_path: str,
        expiration: int = 3600,
        filename: str | None = None,
    ) -> str:
        """Get a URL for downloading a file.

        Args:
            storage_path: The storage path
            expiration: URL expiration time in seconds
            filename: Optional filename for Content-Disposition header

        Returns:
            Download URL (presigned for S3, local path for filesystem)
        """
        pass

    @abstractmethod
    async def list_files(self, prefix: str) -> list[str]:
        """List files with a given prefix.

        Args:
            prefix: Path prefix to filter by

        Returns:
            List of filenames (relative to prefix)
        """
        pass

    @asynccontextmanager
    async def temp_download(self, storage_path: str) -> AsyncIterator[str]:
        """Context manager that downloads a file to a temp location and cleans up.

        Args:
            storage_path: The storage path

        Yields:
            The local file path
        """
        temp_path = await self.download_file(storage_path)
        try:
            yield temp_path
        finally:
            if temp_path != storage_path and os.path.exists(temp_path):
                os.remove(temp_path)


class FilesystemStorage(Storage):
    """Local filesystem storage implementation."""

    async def upload_file(
        self,
        local_path: str,
        storage_path: str,
        content_type: str | None = None,
    ) -> str:
        """Upload a file to local storage (copy if different paths)."""
        if local_path != storage_path:
            os.makedirs(os.path.dirname(storage_path), exist_ok=True)
            if os.path.exists(local_path):
                import shutil

                shutil.copy2(local_path, storage_path)
        return storage_path

    async def upload_bytes(
        self,
        data: bytes,
        storage_path: str,
        content_type: str | None = None,
    ) -> str:
        """Write bytes to local storage."""
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)
        with open(storage_path, "wb") as f:
            f.write(data)
        return storage_path

    async def download_file(
        self,
        storage_path: str,
        local_path: str | None = None,
    ) -> str:
        """Return the storage path (already local)."""
        if not os.path.exists(storage_path):
            raise FileNotFoundError(f"File not found: {storage_path}")
        return storage_path

    async def download_bytes(self, storage_path: str) -> bytes:
        """Read bytes from local storage."""
        with open(storage_path, "rb") as f:
            return f.read()

    async def file_exists(self, storage_path: str) -> bool:
        """Check if file exists locally."""
        return os.path.exists(storage_path)

    async def delete_file(self, storage_path: str) -> None:
        """Delete local file."""
        if os.path.exists(storage_path):
            os.remove(storage_path)

    async def get_file_size(self, storage_path: str) -> int:
        """Get local file size."""
        return os.path.getsize(storage_path)

    async def get_download_url(
        self,
        storage_path: str,
        expiration: int = 3600,
        filename: str | None = None,
    ) -> str:
        """Return the local path (caller will handle serving)."""
        return storage_path

    async def list_files(self, prefix: str) -> list[str]:
        """List files in local directory."""
        base_path = prefix.rstrip("/")
        if not os.path.exists(base_path):
            return []

        files = []
        for item in os.listdir(base_path):
            item_path = os.path.join(base_path, item)
            if os.path.isfile(item_path):
                files.append(item)
        return files

    @asynccontextmanager
    async def temp_download(self, storage_path: str) -> AsyncIterator[str]:
        """For local storage, just yield the path directly."""
        yield storage_path


class S3Storage(Storage):
    """S3 storage implementation."""

    def __init__(self, config: StorageConfig):
        """Initialize S3 storage with configuration."""
        self.config = config

    @asynccontextmanager
    async def _get_client(self):
        """Create an async S3 client context manager."""
        from botocore.config import Config as BotoConfig

        session = aioboto3.Session()

        boto_config = BotoConfig(
            s3={"addressing_style": "path" if self.config.use_path_style else "auto"},
            signature_version="s3v4",
        )

        client_kwargs = {
            "region_name": self.config.region,
            "aws_access_key_id": self.config.access_key_id,
            "aws_secret_access_key": self.config.secret_access_key,
            "config": boto_config,
        }

        if self.config.endpoint_url:
            client_kwargs["endpoint_url"] = self.config.endpoint_url

        async with session.client("s3", **client_kwargs) as client:
            yield client

    async def upload_file(
        self,
        local_path: str,
        storage_path: str,
        content_type: str | None = None,
    ) -> str:
        """Upload a file to S3."""
        if not content_type:
            content_type, _ = mimetypes.guess_type(os.path.basename(storage_path))

        async with self._get_client() as s3:
            extra_args = {}
            if content_type:
                extra_args["ContentType"] = content_type

            await s3.upload_file(
                local_path,
                self.config.bucket_name,
                storage_path,
                ExtraArgs=extra_args or None,
            )

        return storage_path

    async def upload_bytes(
        self,
        data: bytes,
        storage_path: str,
        content_type: str | None = None,
    ) -> str:
        """Upload bytes to S3."""
        if not content_type:
            content_type, _ = mimetypes.guess_type(os.path.basename(storage_path))

        async with self._get_client() as s3:
            extra_args = {}
            if content_type:
                extra_args["ContentType"] = content_type

            await s3.put_object(
                Bucket=self.config.bucket_name,
                Key=storage_path,
                Body=data,
                **(extra_args if extra_args else {}),
            )

        return storage_path

    async def download_file(
        self,
        storage_path: str,
        local_path: str | None = None,
    ) -> str:
        """Download a file from S3."""
        if local_path is None:
            suffix = os.path.splitext(storage_path)[1]
            with NamedTemporaryFile(delete=False, suffix=suffix) as temp:
                local_path = temp.name

        async with self._get_client() as s3:
            response = await s3.get_object(Bucket=self.config.bucket_name, Key=storage_path)
            body = response["Body"]

            with open(local_path, "wb") as out_file:
                while True:
                    chunk = await body.read(1024 * 1024)
                    if not chunk:
                        break
                    out_file.write(chunk)

        return local_path

    async def download_bytes(self, storage_path: str) -> bytes:
        """Download bytes from S3."""
        async with self._get_client() as s3:
            response = await s3.get_object(Bucket=self.config.bucket_name, Key=storage_path)
            async with response["Body"] as stream:
                return await stream.read()

    async def file_exists(self, storage_path: str) -> bool:
        """Check if file exists in S3."""
        try:
            async with self._get_client() as s3:
                await s3.head_object(Bucket=self.config.bucket_name, Key=storage_path)
            return True
        except Exception:
            return False

    async def delete_file(self, storage_path: str) -> None:
        """Delete file from S3."""
        async with self._get_client() as s3:
            await s3.delete_object(Bucket=self.config.bucket_name, Key=storage_path)

    async def get_file_size(self, storage_path: str) -> int:
        """Get S3 file size."""
        async with self._get_client() as s3:
            response = await s3.head_object(Bucket=self.config.bucket_name, Key=storage_path)
            return response["ContentLength"]

    async def get_download_url(
        self,
        storage_path: str,
        expiration: int = 3600,
        filename: str | None = None,
    ) -> str:
        """Generate presigned URL for S3."""
        params = {
            "Bucket": self.config.bucket_name,
            "Key": storage_path,
        }

        if filename and not self.config.skip_content_disposition:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'

        async with self._get_client() as s3:
            url = await s3.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=expiration,
            )

        return url

    async def list_files(self, prefix: str) -> list[str]:
        """List files in S3 with prefix."""
        files = []
        prefix_with_slash = prefix if prefix.endswith("/") else f"{prefix}/"

        async with self._get_client() as s3:
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(
                Bucket=self.config.bucket_name, Prefix=prefix_with_slash
            ):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    filename = key[len(prefix_with_slash) :]
                    if filename and "/" not in filename:
                        files.append(filename)

        return files


def get_storage() -> Storage:
    """Factory function to get the appropriate storage backend.

    Returns:
        Storage instance based on configuration
    """
    config = get_storage_config()
    if config.use_s3 and config.bucket_name:
        return S3Storage(config)
    return FilesystemStorage()


# =============================================================================
# New user/job/source-based path helpers
# =============================================================================


def get_source_key(user_id: int, source_id: str, filename: str) -> str:
    """Generate an S3 key for source files (video, frames).

    Structure: {user_id}/sources/{source_id}/{filename}

    Args:
        user_id: The user's ID
        source_id: The source identifier (content hash or panopto delivery ID)
        filename: The filename (e.g., 'video.mp4' or frame UUID)

    Returns:
        The S3 key for the source file
    """
    return f"{user_id}/sources/{source_id}/{filename}"


def get_source_local_path(user_id: int, source_id: str, filename: str) -> str:
    """Get local filesystem path for source files.

    Structure: {FRAMES_DIR}/{user_id}/sources/{source_id}/{filename}

    Args:
        user_id: The user's ID
        source_id: The source identifier
        filename: The filename

    Returns:
        The local filesystem path
    """
    base_dir = Path(settings.FRAMES_DIR)
    return str(base_dir / str(user_id) / "sources" / source_id / filename)


def get_job_key(user_id: int, job_id: int, filename: str) -> str:
    """Generate an S3 key for job artifacts (PDF, Excel, etc.).

    Structure: {user_id}/jobs/{job_id}/{filename}

    Args:
        user_id: The user's ID
        job_id: The job's ID
        filename: The filename (e.g., 'handout.pdf')

    Returns:
        The S3 key for the job artifact
    """
    return f"{user_id}/jobs/{job_id}/{filename}"


def get_job_local_path(user_id: int, job_id: int, filename: str) -> str:
    """Get local filesystem path for job artifacts.

    Structure: {OUTPUT_DIR}/{user_id}/jobs/{job_id}/{filename}

    Args:
        user_id: The user's ID
        job_id: The job's ID
        filename: The filename

    Returns:
        The local filesystem path
    """
    base_dir = Path(settings.OUTPUT_DIR)
    return str(base_dir / str(user_id) / "jobs" / str(job_id) / filename)


def get_source_path(user_id: int, source_id: str, filename: str) -> str:
    """Get storage path for source files (S3 key or local path).

    Args:
        user_id: The user's ID
        source_id: The source identifier
        filename: The filename

    Returns:
        S3 key if S3 enabled, otherwise local path
    """
    if is_s3_enabled():
        return get_source_key(user_id, source_id, filename)
    return get_source_local_path(user_id, source_id, filename)


def get_job_path(user_id: int, job_id: int, filename: str) -> str:
    """Get storage path for job artifacts (S3 key or local path).

    Args:
        user_id: The user's ID
        job_id: The job's ID
        filename: The filename

    Returns:
        S3 key if S3 enabled, otherwise local path
    """
    if is_s3_enabled():
        return get_job_key(user_id, job_id, filename)
    return get_job_local_path(user_id, job_id, filename)


# =============================================================================
# Legacy path helpers (deprecated - use get_source_key/get_job_key instead)
# =============================================================================


def get_s3_key(storage_type: StorageType, filename: str, source_id: str | None = None) -> str:
    """Generate an S3 key for a file.

    DEPRECATED: Use get_source_key() for source files or get_job_key() for artifacts.

    Args:
        storage_type: Type of storage (input, output, frames)
        filename: The filename
        source_id: Optional source ID for frames (used as subdirectory)

    Returns:
        The S3 key for the file
    """
    config = get_storage_config()
    prefix_map = {
        "input": config.input_prefix,
        "output": config.output_prefix,
        "frames": config.frames_prefix,
    }
    prefix = prefix_map[storage_type]

    if storage_type == "frames" and source_id:
        return f"{prefix}{source_id}/{filename}"

    return f"{prefix}{filename}"


def get_local_path(storage_type: StorageType, filename: str, source_id: str | None = None) -> str:
    """Get local filesystem path for a file.

    DEPRECATED: Use get_source_local_path() or get_job_local_path() instead.

    Args:
        storage_type: Type of storage (input, output, frames)
        filename: The filename
        source_id: Optional source ID for frames (used as subdirectory)

    Returns:
        The local filesystem path
    """
    dir_map = {
        "input": settings.INPUT_DIR,
        "output": settings.OUTPUT_DIR,
        "frames": settings.FRAMES_DIR,
    }
    base_dir = Path(dir_map[storage_type])

    if storage_type == "frames" and source_id:
        return str(base_dir / source_id / filename)

    return str(base_dir / filename)


async def upload_file(
    local_path: str,
    storage_type: StorageType,
    filename: str | None = None,
    source_id: str | None = None,
) -> str:
    """Upload a file to storage.

    Args:
        local_path: Path to the local file to upload
        storage_type: Type of storage (input, output, frames)
        filename: Optional filename (defaults to basename of local_path)
        source_id: Optional source ID for organizing files (used for frames)

    Returns:
        The storage path (S3 key or local path)
    """
    if filename is None:
        filename = os.path.basename(local_path)

    storage = get_storage()

    if isinstance(storage, FilesystemStorage):
        storage_path = get_local_path(storage_type, filename, source_id)
    else:
        storage_path = get_s3_key(storage_type, filename, source_id)

    return await storage.upload_file(local_path, storage_path)


async def upload_bytes(
    data: bytes,
    storage_type: StorageType,
    filename: str,
    source_id: str | None = None,
    content_type: str | None = None,
) -> str:
    """Upload bytes data to storage.

    Args:
        data: The bytes to upload
        storage_type: Type of storage (input, output, frames)
        filename: The filename
        source_id: Optional source ID for organizing files
        content_type: Optional content type

    Returns:
        The storage path (S3 key or local path)
    """
    storage = get_storage()

    if isinstance(storage, FilesystemStorage):
        storage_path = get_local_path(storage_type, filename, source_id)
    else:
        storage_path = get_s3_key(storage_type, filename, source_id)

    return await storage.upload_bytes(data, storage_path, content_type)


async def download_file(
    storage_path: str,
    local_path: str | None = None,
    storage_type: StorageType | None = None,
) -> str:
    """Download a file from storage to local filesystem.

    Args:
        storage_path: The storage path (S3 key or local path)
        local_path: Optional destination local path
        storage_type: Optional storage type for path resolution

    Returns:
        The local file path
    """
    storage = get_storage()
    return await storage.download_file(storage_path, local_path)


async def download_bytes(storage_path: str) -> bytes:
    """Download a file from storage as bytes.

    Args:
        storage_path: The storage path (S3 key or local path)

    Returns:
        The file contents as bytes
    """
    storage = get_storage()
    return await storage.download_bytes(storage_path)


async def file_exists(
    storage_path: str = "",
    storage_type: StorageType | None = None,
    filename: str | None = None,
    source_id: str | None = None,
) -> bool:
    """Check if a file exists in storage.

    Args:
        storage_path: Direct storage path (S3 key or local path)
        storage_type: Optional storage type for path building
        filename: Optional filename for path building
        source_id: Optional source ID for path building

    Returns:
        True if the file exists
    """
    storage = get_storage()

    # Build path if components provided
    if storage_type and filename:
        if isinstance(storage, FilesystemStorage):
            storage_path = get_local_path(storage_type, filename, source_id)
        else:
            storage_path = get_s3_key(storage_type, filename, source_id)

    return await storage.file_exists(storage_path)


async def delete_file(storage_path: str) -> None:
    """Delete a file from storage.

    Args:
        storage_path: The storage path (S3 key or local path)
    """
    storage = get_storage()
    await storage.delete_file(storage_path)


async def get_file_size(storage_path: str) -> int:
    """Get the size of a file in storage.

    Args:
        storage_path: The storage path (S3 key or local path)

    Returns:
        File size in bytes
    """
    storage = get_storage()
    return await storage.get_file_size(storage_path)


async def generate_presigned_url(
    storage_path: str,
    expiration: int = 3600,
    response_content_disposition: str | None = None,
) -> str:
    """Generate a presigned URL for downloading a file.

    Args:
        storage_path: The storage path (S3 key)
        expiration: URL expiration time in seconds (default 1 hour)
        response_content_disposition: Optional Content-Disposition header value
            (ignored if S3_SKIP_CONTENT_DISPOSITION is set for S3-compatible services)

    Returns:
        The presigned URL, or the local path if S3 is disabled
    """
    storage = get_storage()

    # Extract filename from Content-Disposition header if provided
    filename = None
    if response_content_disposition:
        # Parse: attachment; filename="example.pdf"
        parts = response_content_disposition.split("filename=")
        if len(parts) > 1:
            filename = parts[1].strip('"')

    return await storage.get_download_url(storage_path, expiration, filename)


@asynccontextmanager
async def temp_download(storage_path: str) -> AsyncIterator[str]:
    """Context manager that downloads a file to a temp location and cleans up.

    Args:
        storage_path: The storage path (S3 key or local path)

    Yields:
        The local file path (temp file for S3, original for local)
    """
    storage = get_storage()
    async with storage.temp_download(storage_path) as local_path:
        yield local_path


@asynccontextmanager
async def temp_directory() -> AsyncIterator[str]:
    """Context manager for a temporary directory that is cleaned up after use.

    Yields:
        Path to the temporary directory
    """
    with TemporaryDirectory() as temp_dir:
        yield temp_dir


async def list_files(
    storage_type: StorageType,
    prefix: str = "",
    source_id: str | None = None,
) -> list[str]:
    """List files in storage.

    Args:
        storage_type: Type of storage (input, output, frames)
        prefix: Optional prefix filter within the storage type
        source_id: Optional source ID for frames

    Returns:
        List of filenames (not full paths/keys)
    """
    storage = get_storage()

    if isinstance(storage, FilesystemStorage):
        base_path = get_local_path(storage_type, "", source_id).rstrip("/")
        return await storage.list_files(base_path)
    else:
        s3_prefix = get_s3_key(storage_type, "", source_id)
        if prefix:
            s3_prefix = f"{s3_prefix}{prefix}"
        return await storage.list_files(s3_prefix)


async def upload_source_file(
    local_path: str,
    user_id: int,
    source_id: str,
    filename: str | None = None,
) -> str:
    """Upload a file to user's source storage.

    Args:
        local_path: Path to the local file to upload
        user_id: The user's ID
        source_id: The source identifier
        filename: Optional filename (defaults to basename of local_path)

    Returns:
        The storage path (S3 key or local path)
    """
    if filename is None:
        filename = os.path.basename(local_path)

    storage = get_storage()
    storage_path = get_source_path(user_id, source_id, filename)

    return await storage.upload_file(local_path, storage_path)


async def upload_job_file(
    local_path: str,
    user_id: int,
    job_id: int,
    filename: str | None = None,
) -> str:
    """Upload a file to user's job storage.

    Args:
        local_path: Path to the local file to upload
        user_id: The user's ID
        job_id: The job's ID
        filename: Optional filename (defaults to basename of local_path)

    Returns:
        The storage path (S3 key or local path)
    """
    if filename is None:
        filename = os.path.basename(local_path)

    storage = get_storage()
    storage_path = get_job_path(user_id, job_id, filename)

    return await storage.upload_file(local_path, storage_path)


def sync_upload_file(
    local_path: str,
    storage_type: StorageType,
    filename: str | None = None,
    source_id: str | None = None,
) -> str:
    """Synchronous version of upload_file for use in sync contexts."""
    return asyncio.get_event_loop().run_until_complete(
        upload_file(local_path, storage_type, filename, source_id)
    )


def sync_download_file(
    storage_path: str,
    local_path: str | None = None,
) -> str:
    """Synchronous version of download_file for use in sync contexts."""
    return asyncio.get_event_loop().run_until_complete(download_file(storage_path, local_path))


def sync_file_exists(storage_path: str) -> bool:
    """Synchronous version of file_exists for use in sync contexts."""
    return asyncio.get_event_loop().run_until_complete(file_exists(storage_path))


def sync_get_file_size(storage_path: str) -> int:
    """Synchronous version of get_file_size for use in sync contexts."""
    return asyncio.get_event_loop().run_until_complete(get_file_size(storage_path))
