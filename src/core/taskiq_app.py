"""
Taskiq broker configuration for Handout Generator.

Sets up Redis broker with result backend and PipelineMiddleware for task chaining.
"""

import os

# Django setup must happen before importing tasks
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "handout_generator.settings")

import django

django.setup()

from taskiq_pipelines import PipelineMiddleware
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from .middleware import PipelineErrorMiddleware

# Redis configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Create the result backend
result_backend = RedisAsyncResultBackend(
    redis_url=REDIS_URL,
    result_ex_time=60 * 60 * 24,  # Results expire after 24 hours
)

# Create the broker with middlewares
broker = (
    ListQueueBroker(
        url=REDIS_URL,
        queue_name="handout_generator",
    )
    .with_result_backend(result_backend)
    .with_middlewares(
        PipelineErrorMiddleware(),
        PipelineMiddleware(),
    )
)


# Import tasks so they are registered with the broker
from . import tasks  # noqa: F401


@broker.on_event("worker_startup")
async def on_worker_startup(state):
    """Initialize resources when worker starts."""
    import redis.asyncio as aioredis

    # Store Redis connection for pub/sub in state
    state.redis = await aioredis.from_url(REDIS_URL)


@broker.on_event("worker_shutdown")
async def on_worker_shutdown(state):
    """Cleanup when worker shuts down."""
    if hasattr(state, "redis"):
        await state.redis.close()
