"""
S3 Storage utilities for file operations.

This module provides a unified interface for file storage operations that works
with both local filesystem and S3 storage, depending on configuration.
"""

import logging
import mimetypes
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

import aioboto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.exceptions import StorageError


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
    """S3 storage implementation with connection pooling."""

    _session: aioboto3.Session | None = None

    def __init__(self, config: StorageConfig):
        """Initialize S3 storage with configuration."""
        self.config = config

    @classmethod
    def get_session(cls) -> aioboto3.Session:
        """Get or create the singleton aioboto3 session for connection pooling."""
        if cls._session is None:
            cls._session = aioboto3.Session()
        return cls._session

    @asynccontextmanager
    async def _get_client(self):
        """Create an async S3 client context manager with connection pooling."""
        from botocore.config import Config as BotoConfig

        session = self.get_session()

        boto_config = BotoConfig(
            s3={"addressing_style": "path" if self.config.use_path_style else "auto"},
            signature_version="s3v4",
            max_pool_connections=50,
            connect_timeout=5,
            read_timeout=60,
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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ClientError, BotoCoreError)),
        reraise=True,
    )
    async def upload_file(
        self,
        local_path: str,
        storage_path: str,
        content_type: str | None = None,
    ) -> str:
        """Upload a file to S3."""
        try:
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
        except (ClientError, BotoCoreError) as e:
            raise StorageError(f"Failed to upload file to S3: {storage_path}") from e

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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ClientError, BotoCoreError)),
        reraise=True,
    )
    async def download_file(
        self,
        storage_path: str,
        local_path: str | None = None,
    ) -> str:
        """Download a file from S3."""
        try:
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
        except (ClientError, BotoCoreError) as e:
            raise StorageError(f"Failed to download file from S3: {storage_path}") from e

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
        except ClientError as e:
            # 404 means file doesn't exist
            if e.response.get("Error", {}).get("Code") == "404":
                return False
            # Other client errors should be logged but treated as "not found"
            logging.warning(f"S3 error checking file existence: {storage_path}", exc_info=e)
            return False
        except BotoCoreError as e:
            logging.warning(f"S3 error checking file existence: {storage_path}", exc_info=e)
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
# Helper functions for temp operations and storage management
# =============================================================================


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
