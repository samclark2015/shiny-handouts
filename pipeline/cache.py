"""
Durable and thread-safe caching for pipeline stages.

Uses diskcache for persistent, thread-safe storage that survives process restarts.
Cache keys are based on source_id and stage name to allow resuming failed pipelines.
"""

import hashlib
import os
import pickle
from dataclasses import dataclass
from typing import Any

import diskcache

# Default cache directory
CACHE_DIR = os.path.join("data", "cache")

# Global cache instance (thread-safe by default with diskcache)
_cache: diskcache.Cache | None = None


def get_cache() -> diskcache.Cache:
    """Get or create the global cache instance."""
    global _cache
    if _cache is None:
        os.makedirs(CACHE_DIR, exist_ok=True)
        _cache = diskcache.Cache(
            CACHE_DIR,
            size_limit=10 * 1024 * 1024 * 1024,  # 10GB limit
            eviction_policy="least-recently-used",
        )
    return _cache


def close_cache() -> None:
    """Close the cache connection."""
    global _cache
    if _cache is not None:
        _cache.close()
        _cache = None


def clear_cache() -> None:
    """Clear all cached data."""
    cache = get_cache()
    cache.clear()


def _generate_cache_key(source_id: str, stage_name: str) -> str:
    """Generate a unique cache key for a stage result."""
    key_data = f"{source_id}:{stage_name}"
    return hashlib.sha256(key_data.encode()).hexdigest()


@dataclass
class CachedResult:
    """Wrapper for cached stage results with metadata."""

    stage_name: str
    source_id: str
    result: Any


def get_cached_result(source_id: str, stage_name: str) -> Any | None:
    """
    Retrieve a cached result for a specific stage.

    Args:
        source_id: The unique identifier for the source (e.g., video hash)
        stage_name: The name of the pipeline stage

    Returns:
        The cached result if found, None otherwise
    """
    cache = get_cache()
    key = _generate_cache_key(source_id, stage_name)

    try:
        cached: CachedResult | None = cache.get(key)
        if cached is not None:
            return cached.result
    except (pickle.PickleError, Exception):
        # If there's an error reading cache, treat as cache miss
        pass

    return None


def set_cached_result(source_id: str, stage_name: str, result: Any) -> None:
    """
    Store a result in the cache.

    Args:
        source_id: The unique identifier for the source
        stage_name: The name of the pipeline stage
        result: The result to cache
    """
    cache = get_cache()
    key = _generate_cache_key(source_id, stage_name)

    cached = CachedResult(
        stage_name=stage_name,
        source_id=source_id,
        result=result,
    )

    try:
        cache.set(key, cached)
    except (pickle.PickleError, Exception) as e:
        # Log but don't fail if caching fails
        print(f"Warning: Failed to cache result for {stage_name}: {e}")


def invalidate_stage(source_id: str, stage_name: str) -> bool:
    """
    Invalidate a specific cached stage result.

    Args:
        source_id: The unique identifier for the source
        stage_name: The name of the pipeline stage

    Returns:
        True if the key was found and deleted, False otherwise
    """
    cache = get_cache()
    key = _generate_cache_key(source_id, stage_name)
    return cache.delete(key)


def invalidate_source(source_id: str) -> int:
    """
    Invalidate all cached results for a specific source.

    Args:
        source_id: The unique identifier for the source

    Returns:
        Number of keys invalidated
    """
    cache = get_cache()
    count = 0

    # Iterate through all keys and remove those matching the source_id
    for key in list(cache):
        try:
            cached: CachedResult | None = cache.get(key)
            if cached is not None and cached.source_id == source_id:
                cache.delete(key)
                count += 1
        except Exception:
            pass

    return count


def get_cache_stats() -> dict[str, Any]:
    """Get cache statistics."""
    cache = get_cache()
    return {
        "size": len(cache),
        "volume": cache.volume(),
        "directory": CACHE_DIR,
    }
