"""
Redis-based caching for AI function results.

Provides caching functionality for AI function calls to prevent unnecessary API expenses.
"""

import hashlib
import os
import pickle
from typing import Any

import redis

# Redis configuration
REDIS_CACHE_URL = os.environ.get("REDIS_CACHE_URL", "redis://localhost:6379/1")

# Global Redis client instance
_redis_client: redis.Redis | None = None

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


def _generate_ai_cache_key(func_name: str, *args, **kwargs) -> str:
    """
    Generate a unique cache key for an AI function call based on function name and arguments.

    Args:
        func_name: Name of the AI function
        *args: Positional arguments to the function
        **kwargs: Keyword arguments to the function

    Returns:
        A unique hash string for this function call
    """
    # Create a stable representation of the arguments
    # For file paths, use file hash instead of path to detect content changes
    stable_args = []
    for arg in args:
        if isinstance(arg, str) and os.path.exists(arg):
            # Hash file content
            with open(arg, "rb") as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
            stable_args.append(f"file:{file_hash}")
        else:
            stable_args.append(str(arg))

    stable_kwargs = []
    for k, v in sorted(kwargs.items()):
        if isinstance(v, str) and os.path.exists(v):
            # Hash file content
            with open(v, "rb") as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
            stable_kwargs.append((k, f"file:{file_hash}"))
        elif v is None:
            stable_kwargs.append((k, "None"))
        else:
            stable_kwargs.append((k, str(v)))

    # Create cache key from function name and arguments
    key_data = (
        f"ai:{func_name}:{':'.join(stable_args)}:{':'.join(f'{k}={v}' for k, v in stable_kwargs)}"
    )
    return hashlib.sha256(key_data.encode()).hexdigest()


def get_ai_cached_result(func_name: str, *args, **kwargs) -> Any | None:
    """
    Retrieve a cached result for an AI function call.

    Args:
        func_name: Name of the AI function
        *args: Positional arguments that were passed to the function
        **kwargs: Keyword arguments that were passed to the function

    Returns:
        The cached result if found, None otherwise
    """
    client = get_redis_client()
    key = _generate_ai_cache_key(func_name, *args, **kwargs)

    try:
        cached_data = client.get(key)
        if cached_data is not None:
            return pickle.loads(cached_data)
    except (pickle.PickleError, redis.RedisError) as e:
        print(f"AI cache read error for {func_name}: {e}")

    return None


def set_ai_cached_result(func_name: str, result: Any, *args, **kwargs) -> None:
    """
    Store an AI function result in the cache.

    Args:
        func_name: Name of the AI function
        result: The result to cache
        *args: Positional arguments that were passed to the function
        **kwargs: Keyword arguments that were passed to the function
    """
    client = get_redis_client()
    key = _generate_ai_cache_key(func_name, *args, **kwargs)

    try:
        serialized = pickle.dumps(result)
        client.setex(key, CACHE_EXPIRY, serialized)
    except (pickle.PickleError, redis.RedisError) as e:
        print(f"AI cache write error for {func_name}: {e}")
