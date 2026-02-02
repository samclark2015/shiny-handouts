# Storage Abstraction Migration

**Date:** February 2, 2026
**Branch:** celery
**Status:** Completed

This document describes the migration from legacy storage helper functions to the new Storage ABC (Abstract Base Class) pattern.

---

## Overview

The codebase has been fully migrated from legacy storage helper functions that used a `StorageType` enum pattern to a clean ABC-based storage abstraction. This provides better type safety, clearer interfaces, and eliminates deprecated code paths.

---

## Architecture Changes

### Before (Legacy Pattern)

**StorageType Enum Pattern:**
```python
StorageType = Literal["input", "output", "frames"]

# Module-level wrapper functions
async def upload_file(
    local_path: str,
    storage_type: StorageType,  # ❌ Inflexible enum
    filename: str | None = None,
    source_id: str | None = None,
) -> str:
    # Manually routes to correct implementation
    if isinstance(storage, FilesystemStorage):
        storage_path = get_local_path(storage_type, filename, source_id)
    else:
        storage_path = get_s3_key(storage_type, filename, source_id)
    return await storage.upload_file(local_path, storage_path)
```

**Problems:**
- ❌ Tight coupling to specific storage types
- ❌ Manual path construction logic scattered throughout
- ❌ Difficult to add new storage backends
- ❌ Type checking limitations with Literal enums

### After (ABC Pattern)

**Clean Storage Abstraction:**
```python
class Storage(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def upload_file(
        self,
        local_path: str,
        storage_path: str,
        content_type: str | None = None,
    ) -> str:
        """Upload a file to storage."""
        pass

# Implementations
class FilesystemStorage(Storage): ...
class S3Storage(Storage): ...

# Direct usage with proper path helpers
storage = get_storage()
storage_path = get_job_path(user_id, job_id, filename)
await storage.upload_file(local_path, storage_path)
```

**Benefits:**
- ✅ Clean separation of concerns
- ✅ Easy to add new storage backends
- ✅ Type-safe with proper abstract methods
- ✅ Flexible path construction

---

## Migration Changes

### 1. Removed Deprecated Functions

**Module-level wrappers (REMOVED):**
```python
# ❌ These functions have been completely removed:
async def upload_file(local_path, storage_type, ...)  # Used StorageType
async def upload_bytes(data, storage_type, ...)
async def download_file(storage_path, ...)
async def download_bytes(storage_path)
async def file_exists(storage_path, storage_type, ...)
async def delete_file(storage_path)
async def get_file_size(storage_path)
async def generate_presigned_url(storage_path, ...)
async def list_files(storage_type, ...)
```

**Legacy path helpers (REMOVED):**
```python
# ❌ These functions have been completely removed:
def get_s3_key(storage_type, filename, source_id)
def get_local_path(storage_type, filename, source_id)
StorageType = Literal["input", "output", "frames"]  # Type removed
```

### 2. Kept Modern Helper Functions

**New path-based helpers (KEEP USING):**
```python
# ✅ Use these functions instead:
def get_source_path(user_id: int, source_id: str, filename: str) -> str
def get_source_key(user_id: int, source_id: str, filename: str) -> str
def get_source_local_path(user_id: int, source_id: str, filename: str) -> str

def get_job_path(user_id: int, job_id: int, filename: str) -> str
def get_job_key(user_id: int, job_id: int, filename: str) -> str
def get_job_local_path(user_id: int, job_id: int, filename: str) -> str

async def upload_source_file(local_path, user_id, source_id, filename) -> str
async def upload_job_file(local_path, user_id, job_id, filename) -> str

@asynccontextmanager
async def temp_download(storage_path: str) -> AsyncIterator[str]

@asynccontextmanager
async def temp_directory() -> AsyncIterator[str]
```

---

## Migration Examples

### Example 1: File Upload (api.py)

**Before:**
```python
from core.storage import is_s3_enabled, sync_upload_file

# Upload to S3 if enabled
if is_s3_enabled():
    storage_path = sync_upload_file(local_path, "input", filename)
else:
    storage_path = local_path
```

**After:**
```python
from core.storage import get_job_path, get_storage, is_s3_enabled

# Create job first to get ID
job = Job.objects.create(...)

# Upload to proper storage using job ID
if is_s3_enabled():
    storage = get_storage()
    storage_path = get_job_path(request.user.pk, job.pk, filename)
    storage_path = async_to_sync(storage.upload_file)(local_path, storage_path)
    job.input_data = json.dumps({"path": storage_path, "filename": filename})
    job.save(update_fields=["input_data"])
```

### Example 2: Direct Storage Usage (tasks)

**Already Correct (no changes needed):**
```python
from core.storage import get_storage, get_source_path

storage = get_storage()
storage_path = get_source_path(user_id, source_id, "video.mp4")
await storage.upload_file(local_video_path, storage_path)
```

---

## Files Modified

### Core Storage Module
- **src/core/storage.py**
  - Removed ~200 lines of deprecated code
  - Removed `StorageType` Literal type
  - Removed all legacy wrapper functions
  - Kept ABC pattern and modern helpers

### API Views
- **src/core/views/api.py**
  - Updated `upload_file()` to use Storage ABC
  - Uses `get_job_path()` for proper path generation
  - Creates job first, then uploads with job ID

---

## Benefits of This Migration

### 1. **Cleaner Architecture**
- Clear separation between storage interface and implementation
- No more mixed path construction logic
- Single responsibility for each function

### 2. **Type Safety**
- Abstract methods enforce correct implementation
- No more reliance on string literals ("input", "output", "frames")
- Better IDE autocomplete and type checking

### 3. **Flexibility**
- Easy to add new storage backends (Azure, GCS, etc.)
- Path construction is centralized and consistent
- No need to modify existing code to add new backends

### 4. **Maintainability**
- Removed ~200 lines of deprecated code
- Eliminated dual path systems (StorageType vs user/job-based)
- Clear upgrade path for future changes

### 5. **Consistency**
- All code now uses the same pattern
- User/job-based paths throughout
- No legacy exceptions or special cases

---

## Testing Checklist

After deployment, verify:

- [ ] File uploads work correctly (local and S3)
- [ ] Existing jobs can access their artifacts
- [ ] Video downloads function properly
- [ ] Source file caching works
- [ ] Frame extraction and storage operates correctly
- [ ] Artifact generation (PDF, Excel) creates files successfully
- [ ] S3 connection pooling reduces latency
- [ ] No errors in logs about missing storage functions

---

## Future Improvements

With the ABC pattern in place, we can now:

1. **Add new storage backends easily:**
   - Azure Blob Storage
   - Google Cloud Storage
   - SFTP/FTP storage
   - MinIO or other S3-compatible services

2. **Implement storage middleware:**
   - Compression before upload
   - Encryption at rest
   - Virus scanning
   - Automatic backup to secondary storage

3. **Add storage metrics:**
   - Track upload/download times
   - Monitor bandwidth usage
   - Alert on storage failures
   - Analyze storage costs

---

## Summary

The storage abstraction migration successfully:
- ✅ Removed all deprecated StorageType-based functions
- ✅ Converted to clean ABC pattern
- ✅ Updated api.py to use Storage abstraction
- ✅ Maintained backward compatibility for existing stored paths
- ✅ Reduced codebase by ~200 lines
- ✅ Improved type safety and maintainability

All storage operations now go through the Storage ABC, providing a consistent, type-safe interface for file operations across the entire application.
