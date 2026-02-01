"""
S3 Storage utilities for file operations.

This module provides a unified interface for file storage operations that works
with both local filesystem and S3 storage, depending on configuration.
"""

import asyncio
import mimetypes
import os
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


@asynccontextmanager
async def get_s3_client():
    """Create an async S3 client context manager."""
    config = get_storage_config()
    session = aioboto3.Session()

    client_kwargs = {
        "region_name": config.region,
        "aws_access_key_id": config.access_key_id,
        "aws_secret_access_key": config.secret_access_key,
    }

    if config.endpoint_url:
        client_kwargs["endpoint_url"] = config.endpoint_url

    async with session.client("s3", **client_kwargs) as client:
        yield client


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

    if not is_s3_enabled():
        # For local storage, file is already in place or needs to be copied
        dest_path = get_local_path(storage_type, filename, source_id)
        if local_path != dest_path:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            if os.path.exists(local_path):
                import shutil

                shutil.copy2(local_path, dest_path)
        return dest_path

    # Upload to S3
    config = get_storage_config()
    s3_key = get_s3_key(storage_type, filename, source_id)

    content_type, _ = mimetypes.guess_type(filename)

    async with get_s3_client() as s3:
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        await s3.upload_file(local_path, config.bucket_name, s3_key, ExtraArgs=extra_args or None)

    return s3_key


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
    if not is_s3_enabled():
        # Write to local filesystem
        dest_path = get_local_path(storage_type, filename, source_id)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(data)
        return dest_path

    # Upload to S3
    config = get_storage_config()
    s3_key = get_s3_key(storage_type, filename, source_id)

    if not content_type:
        content_type, _ = mimetypes.guess_type(filename)

    async with get_s3_client() as s3:
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        await s3.put_object(
            Bucket=config.bucket_name,
            Key=s3_key,
            Body=data,
            **(extra_args if extra_args else {}),
        )

    return s3_key


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
    if not is_s3_enabled():
        # For local storage, the storage_path IS the local path
        if os.path.exists(storage_path):
            return storage_path
        raise FileNotFoundError(f"File not found: {storage_path}")

    # Download from S3
    config = get_storage_config()

    if local_path is None:
        # Create a temp file
        suffix = os.path.splitext(storage_path)[1]
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            local_path = temp.name

    async with get_s3_client() as s3:
        await s3.download_file(config.bucket_name, storage_path, local_path)

    return local_path


async def download_bytes(storage_path: str) -> bytes:
    """Download a file from storage as bytes.

    Args:
        storage_path: The storage path (S3 key or local path)

    Returns:
        The file contents as bytes
    """
    if not is_s3_enabled():
        with open(storage_path, "rb") as f:
            return f.read()

    config = get_storage_config()

    async with get_s3_client() as s3:
        response = await s3.get_object(Bucket=config.bucket_name, Key=storage_path)
        async with response["Body"] as stream:
            return await stream.read()


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
    # Build path if components provided
    if storage_type and filename:
        if is_s3_enabled():
            storage_path = get_s3_key(storage_type, filename, source_id)
        else:
            storage_path = get_local_path(storage_type, filename, source_id)

    if not is_s3_enabled():
        return os.path.exists(storage_path)

    config = get_storage_config()

    try:
        async with get_s3_client() as s3:
            await s3.head_object(Bucket=config.bucket_name, Key=storage_path)
        return True
    except Exception:
        return False


async def delete_file(storage_path: str) -> None:
    """Delete a file from storage.

    Args:
        storage_path: The storage path (S3 key or local path)
    """
    if not is_s3_enabled():
        if os.path.exists(storage_path):
            os.remove(storage_path)
        return

    config = get_storage_config()

    async with get_s3_client() as s3:
        await s3.delete_object(Bucket=config.bucket_name, Key=storage_path)


async def get_file_size(storage_path: str) -> int:
    """Get the size of a file in storage.

    Args:
        storage_path: The storage path (S3 key or local path)

    Returns:
        File size in bytes
    """
    if not is_s3_enabled():
        return os.path.getsize(storage_path)

    config = get_storage_config()

    async with get_s3_client() as s3:
        response = await s3.head_object(Bucket=config.bucket_name, Key=storage_path)
        return response["ContentLength"]


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

    Returns:
        The presigned URL, or the local path if S3 is disabled
    """
    if not is_s3_enabled():
        # Return local path - caller will need to handle serving
        return storage_path

    config = get_storage_config()

    params = {
        "Bucket": config.bucket_name,
        "Key": storage_path,
    }

    if response_content_disposition:
        params["ResponseContentDisposition"] = response_content_disposition

    async with get_s3_client() as s3:
        url = await s3.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expiration,
        )

    return url


@asynccontextmanager
async def temp_download(storage_path: str) -> AsyncIterator[str]:
    """Context manager that downloads a file to a temp location and cleans up.

    Args:
        storage_path: The storage path (S3 key or local path)

    Yields:
        The local file path (temp file for S3, original for local)
    """
    if not is_s3_enabled():
        # Local storage - just yield the path directly
        yield storage_path
        return

    # S3 storage - download to temp file
    suffix = os.path.splitext(storage_path)[1]
    with NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        temp_path = temp.name

    try:
        await download_file(storage_path, temp_path)
        yield temp_path
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


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
    if not is_s3_enabled():
        base_path = get_local_path(storage_type, "", source_id).rstrip("/")
        if not os.path.exists(base_path):
            return []

        files = []
        for item in os.listdir(base_path):
            if prefix and not item.startswith(prefix):
                continue
            if os.path.isfile(os.path.join(base_path, item)):
                files.append(item)
        return files

    # S3 storage
    config = get_storage_config()
    s3_prefix = get_s3_key(storage_type, "", source_id)
    if prefix:
        s3_prefix = f"{s3_prefix}{prefix}"

    files = []

    async with get_s3_client() as s3:
        paginator = s3.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=config.bucket_name, Prefix=s3_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                # Extract filename from key
                filename = key[len(s3_prefix) :].lstrip("/")
                if filename and "/" not in filename:  # Only direct children
                    files.append(filename)

    return files


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

    if not is_s3_enabled():
        dest_path = get_source_local_path(user_id, source_id, filename)
        if local_path != dest_path:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            if os.path.exists(local_path):
                import shutil

                shutil.copy2(local_path, dest_path)
        return dest_path

    config = get_storage_config()
    s3_key = get_source_key(user_id, source_id, filename)

    content_type, _ = mimetypes.guess_type(filename)

    async with get_s3_client() as s3:
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        await s3.upload_file(local_path, config.bucket_name, s3_key, ExtraArgs=extra_args or None)

    return s3_key


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

    if not is_s3_enabled():
        dest_path = get_job_local_path(user_id, job_id, filename)
        if local_path != dest_path:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            if os.path.exists(local_path):
                import shutil

                shutil.copy2(local_path, dest_path)
        return dest_path

    config = get_storage_config()
    s3_key = get_job_key(user_id, job_id, filename)

    content_type, _ = mimetypes.guess_type(filename)

    async with get_s3_client() as s3:
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        await s3.upload_file(local_path, config.bucket_name, s3_key, ExtraArgs=extra_args or None)

    return s3_key


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
