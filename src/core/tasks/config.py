"""
Configuration and constants for the task pipeline.
"""

import os

from taskiq_pipelines import PipelineMiddleware
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from core.middleware import PipelineErrorMiddleware

# Directory configuration
IN_DIR = os.path.join("data", "input")
OUT_DIR = os.path.join("data", "output")
FRAMES_DIR = os.path.join("data", "frames")

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

# Ensure directories exist
os.makedirs(IN_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(FRAMES_DIR, exist_ok=True)


# Pipeline stage weights (must sum to 1.0)
# Note: generate_artifacts is a parallel stage that includes spreadsheet, vignette, and mindmap
STAGE_WEIGHTS = {
    "generate_context": 0.02,  # 2%
    "download_video": 0.15,  # 15%
    "extract_captions": 0.15,  # 15%
    "match_frames": 0.15,  # 15%
    "transform_slides_with_ai": 0.15,  # 15%
    "generate_output": 0.10,  # 10%
    "compress_pdf": 0.08,  # 8%
    "generate_artifacts": 0.18,  # 18% (parallel: spreadsheet + vignette + mindmap)
    "finalize_job": 0.02,  # 2%
}

# Calculate cumulative stage start positions
STAGE_START_PROGRESS: dict[str, float] = {}
_cumulative = 0.0
for stage, weight in STAGE_WEIGHTS.items():
    STAGE_START_PROGRESS[stage] = _cumulative
    _cumulative += weight


# Frame comparison settings
FRAME_SCALE_FACTOR = 0.5
FRAME_SIMILARITY_THRESHOLD = 0.85
