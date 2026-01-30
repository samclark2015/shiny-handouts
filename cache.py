"""
Redis-based caching for pipeline stages.

Replaces the diskcache implementation with Redis for distributed caching.
Cache keys are based on source_id and stage name to allow resuming failed pipelines.
"""

import hashlib
import os
import pickle
from typing import Any, Optional

import redis

# Redis configuration
REDIS_CACHE_URL = os.environ.get("REDIS_CACHE_URL", "redis://localhost:6379/1")

# Global Redis client instance
_redis_client: Optional[redis.Redis] = None

# Cache expiration time (7 days)
CACHE_EXPIRY = 60 * 60 * 24 * 7


def get_redis_client() -> redis.Redis:
    """Get or create the Redis client instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_CACHE_URL, decode_responses=False)
    return _redis_client


def close_cache() -> None:
    """Close the Redis connection."""
    global _redis_client
    if _redis_client is not None:
        _redis_client.close()
        _redis_client = None


def clear_cache() -> None:
    """Clear all cached data."""
    client = get_redis_client()
    client.flushdb()


def _generate_cache_key(source_id: str, stage_name: str) -> str:
    """Generate a unique cache key for a stage result."""
    key_data = f"pipeline:{source_id}:{stage_name}"
    return hashlib.sha256(key_data.encode()).hexdigest()


def get_cached_result(source_id: str, stage_name: str) -> Optional[Any]:
    """
    Retrieve a cached result for a specific stage.

    Args:
        source_id: The unique identifier for the source (e.g., video hash)
        stage_name: The name of the pipeline stage

    Returns:
        The cached result if found, None otherwise
    """
    client = get_redis_client()
    key = _generate_cache_key(source_id, stage_name)

    try:
        cached_data = client.get(key)
        if cached_data is not None:
            return pickle.loads(cached_data)
    except (pickle.PickleError, redis.RedisError) as e:
        # If there's an error reading cache, treat as cache miss
        print(f"Cache read error: {e}")

    return None


def set_cached_result(source_id: str, stage_name: str, result: Any) -> None:
    """
    Store a result in the cache.

    Args:
        source_id: The unique identifier for the source
        stage_name: The name of the pipeline stage
        result: The result to cache
    """
    client = get_redis_client()
    key = _generate_cache_key(source_id, stage_name)

    try:
        serialized = pickle.dumps(result)
        client.setex(key, CACHE_EXPIRY, serialized)
    except (pickle.PickleError, redis.RedisError) as e:
        # Log error but don't fail the pipeline
        print(f"Cache write error: {e}")


def delete_cached_result(source_id: str, stage_name: str) -> bool:
    """
    Delete a cached result.

    Args:
        source_id: The unique identifier for the source
        stage_name: The name of the pipeline stage

    Returns:
        True if the key was deleted, False otherwise
    """
    client = get_redis_client()
    key = _generate_cache_key(source_id, stage_name)

    try:
        return client.delete(key) > 0
    except redis.RedisError as e:
        print(f"Cache delete error: {e}")
        return False


def get_all_stage_keys(source_id: str) -> list[str]:
    """
    Get all cache keys for a given source.

    Args:
        source_id: The unique identifier for the source

    Returns:
        List of stage names that have cached results
    """
    # Note: This requires storing metadata about stages
    # For now, return an empty list - full implementation would track this
    return []


class CacheContext:
    """Context manager for cache operations with a specific source_id."""

    def __init__(self, source_id: str):
        self.source_id = source_id

    def get(self, stage_name: str) -> Optional[Any]:
        """Get cached result for a stage."""
        return get_cached_result(self.source_id, stage_name)

    def set(self, stage_name: str, result: Any) -> None:
        """Set cached result for a stage."""
        set_cached_result(self.source_id, stage_name, result)

    def delete(self, stage_name: str) -> bool:
        """Delete cached result for a stage."""
        return delete_cached_result(self.source_id, stage_name)
