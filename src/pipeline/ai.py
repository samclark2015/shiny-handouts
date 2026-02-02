import base64
import json
import logging
import os
import time
from decimal import Decimal
from functools import wraps
from io import BytesIO
from pathlib import Path
from typing import cast

from django.conf import settings
from openai import AsyncOpenAI
from pydub import AudioSegment

from core.cache import get_ai_cached_result, set_ai_cached_result

from .helpers import Caption, read_prompt
from .schemas import MindmapResponse, StudyTable, VignetteQuestions

FAST_MODEL = "gpt-4.1-nano"
SMART_MODEL = "gpt-5-mini"

key = os.environ["OPENAI_API_KEY"]

# OpenAI client for all API calls
client = AsyncOpenAI(api_key=key)

# Model pricing in USD per 1M tokens (input/output)
MODEL_PRICING = {
    "gpt-4.1-nano": (0.10, 0.40),  # Input, Output pricing
    "gpt-5-mini": (0.25, 2.00),  # Input, Output pricing
    "whisper-1": (0, 0.006),  # Per minute pricing
}


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    """Calculate estimated cost for an API call."""
    if model not in MODEL_PRICING:
        return Decimal("0.00")

    input_price, output_price = MODEL_PRICING[model]
    input_cost = Decimal(str(prompt_tokens)) * Decimal(str(input_price)) / Decimal("1000000")
    output_cost = Decimal(str(completion_tokens)) * Decimal(str(output_price)) / Decimal("1000000")
    return input_cost + output_cost


async def track_ai_request(
    function_name: str,
    model: str,
    user_id: int | None = None,
    job_id: int | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    duration_ms: int | None = None,
    cached: bool = False,
    success: bool = True,
    error_message: str | None = None,
):
    """Track an AI request in the database."""
    from core.models import AIRequest

    total_tokens = prompt_tokens + completion_tokens
    estimated_cost = calculate_cost(model, prompt_tokens, completion_tokens)

    await AIRequest.objects.acreate(
        function_name=function_name,
        model=model,
        user_id=user_id,
        job_id=job_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost,
        duration_ms=duration_ms,
        cached=cached,
        success=success,
        error_message=error_message,
    )


def ai_checkpoint(func):
    """
    Decorator to cache AI function results to save tokens.

    This caches the result based on the function name and arguments,
    automatically skipping expensive AI calls if the same inputs are provided again.
    Also tracks all requests in the database for cost analysis.

    The decorated function should accept user_id and job_id as keyword arguments.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        func_name = func.__name__
        start_time = time.time()

        # Extract tracking context from kwargs
        cache_kwargs = kwargs.copy()
        user_id = cache_kwargs.pop("user_id")
        job_id = cache_kwargs.pop("job_id")

        # Try to get cached result
        cached = get_ai_cached_result(func_name, *args, **cache_kwargs)
        if cached is not None:
            logging.info(f"[AI Checkpoint] Using cached result for {func_name}")
            # Track as cached request (no tokens used)
            duration_ms = int((time.time() - start_time) * 1000)
            await track_ai_request(
                function_name=func_name,
                model="cached",
                user_id=user_id,
                job_id=job_id,
                cached=True,
                duration_ms=duration_ms,
            )
            return cached

        # Execute the function and cache the result
        logging.info(f"[AI Checkpoint] Executing {func_name} (no cache hit)")
        try:
            result = await func(*args, **kwargs)
            set_ai_cached_result(func_name, result, *args, **cache_kwargs)
        except Exception as e:
            error_msg = str(e)
            # Track failed request
            duration_ms = int((time.time() - start_time) * 1000)
            await track_ai_request(
                function_name=func_name,
                model="unknown",
                user_id=user_id,
                job_id=job_id,
                success=False,
                error_message=error_msg,
                duration_ms=duration_ms,
            )
            raise

        return result

    return wrapper


@ai_checkpoint
async def generate_captions(
    video_path: str, user_id: int | None = None, job_id: int | None = None
) -> list[Caption]:
    start_time = time.time()

    video: AudioSegment = AudioSegment.from_file(video_path, format="mp4")
    audio: AudioSegment = video.set_channels(1).set_frame_rate(16000).set_sample_width(2)

    output = BytesIO()
    audio.export(output, format="mp3")

    output.seek(0)
    output.name = "audio.mp3"
    resp = await client.audio.transcriptions.create(
        file=output,
        model="whisper-1",
        response_format="verbose_json",
        timestamp_granularities=["segment"],
        language="en",
    )

    segs = resp.segments
    if not segs:
        raise ValueError("No segments found in the response")

    captions = [Caption(text=seg.text, timestamp=seg.start) for seg in segs if seg.text]

    # Track the request (Whisper doesn't return token counts, estimate from duration)
    duration_ms = int((time.time() - start_time) * 1000)
    audio_duration_minutes = round(len(audio) / 1000.0 / 60.0)
    await track_ai_request(
        function_name="generate_captions",
        model="whisper-1",
        user_id=user_id,
        job_id=job_id,
        prompt_tokens=0,
        completion_tokens=audio_duration_minutes,
        duration_ms=duration_ms,
    )

    return captions


@ai_checkpoint
async def clean_transcript(
    content: str, user_id: int | None = None, job_id: int | None = None
) -> str:
    start_time = time.time()
    prompt = read_prompt("clean_transcript")

    response = await client.responses.create(
        model=FAST_MODEL,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": content},
        ],
    )

    # Track the request
    duration_ms = int((time.time() - start_time) * 1000)
    usage = getattr(response, "usage", None)
    if usage:
        await track_ai_request(
            function_name="clean_transcript",
            model=FAST_MODEL,
            user_id=user_id,
            job_id=job_id,
            prompt_tokens=getattr(usage, "input_tokens", 0),
            completion_tokens=getattr(usage, "output_tokens", 0),
            duration_ms=duration_ms,
        )

    return response.output_text


@ai_checkpoint
async def gen_keypoints(
    content: str, slide_path: str, user_id: int | None = None, job_id: int | None = None
) -> str:
    start_time = time.time()
    prompt = read_prompt("gen_keypoints")

    # Read and encode the image
    with open(slide_path, "rb") as image_file:
        image_data = base64.b64encode(image_file.read()).decode("utf-8")

    # Determine image format
    image_ext = Path(slide_path).suffix.lower().lstrip(".")
    if image_ext == "jpg":
        image_ext = "jpeg"

    response = await client.responses.create(
        model=SMART_MODEL,
        input=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": content},
                    {
                        "type": "input_image",
                        "detail": "auto",
                        "image_url": f"data:image/jpeg;base64,{image_data}",
                    },
                ],
            },
        ],
    )

    # Track the request
    duration_ms = int((time.time() - start_time) * 1000)
    usage = getattr(response, "usage", None)
    if usage:
        await track_ai_request(
            function_name="gen_keypoints",
            model=SMART_MODEL,
            user_id=user_id,
            job_id=job_id,
            prompt_tokens=getattr(usage, "input_tokens", 0),
            completion_tokens=getattr(usage, "output_tokens", 0),
            duration_ms=duration_ms,
        )

    return response.output_text


@ai_checkpoint
async def generate_title(html: str, user_id: int | None = None, job_id: int | None = None) -> str:
    start_time = time.time()
    prompt = read_prompt("generate_title")
    full_prompt = f"{prompt}\nHTML:\n\n{html}"

    response = await client.responses.create(
        model=FAST_MODEL,
        input=[
            {"role": "user", "content": full_prompt},
        ],
    )

    # Track the request
    duration_ms = int((time.time() - start_time) * 1000)
    usage = getattr(response, "usage", None)
    if usage:
        await track_ai_request(
            function_name="generate_title",
            model=FAST_MODEL,
            user_id=user_id,
            job_id=job_id,
            prompt_tokens=getattr(usage, "input_tokens", 0),
            completion_tokens=getattr(usage, "output_tokens", 0),
            duration_ms=duration_ms,
        )

    return response.output_text


def _build_column_schema(columns: list[dict] | None) -> dict:
    """Build the column configuration section for the spreadsheet prompt."""
    if not columns:
        default_columns_path = settings.BASE_DIR / "prompts" / "default_spreadsheet_columns.json"
        with open(default_columns_path) as f:
            columns = json.load(f)

    columns = cast(list[dict], columns)
    names = [col["name"] for col in columns]
    properties = {
        col["name"]: {"type": "string", "description": col["description"]} for col in columns
    }
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.org/schemas/study-table.schema.json",
        "title": "Study Table (Object Wrapper with Rows Array)",
        "type": "object",
        "additionalProperties": False,
        "required": ["rows"],
        "properties": {
            "rows": {
                "type": "array",
                "description": "Array of CSV rows. Each item maps 1:1 to a CSV row with the specified headers.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": names,
                    "properties": properties,
                },
            }
        },
    }
    return schema


@ai_checkpoint
async def generate_spreadsheet_helper(
    filename: str,
    custom_prompt: str | None = None,
    custom_columns: list[dict] | None = None,
    user_id: int | None = None,
    job_id: int | None = None,
) -> StudyTable:
    """Generate a study table from a PDF file.

    Args:
        filename: Path to the PDF file.
        custom_prompt: Optional custom prompt to use instead of default.
        custom_columns: Optional custom column configuration for the LLM.
        user_id: User ID for tracking.
        job_id: Job ID for tracking.
    """
    start_time = time.time()
    prompt = custom_prompt or read_prompt("generate_spreadsheet")

    schema = _build_column_schema(custom_columns)

    # Read and encode the PDF
    with open(filename, "rb") as pdf_file:
        pdf_data = base64.b64encode(pdf_file.read()).decode("utf-8")

    response = await client.responses.create(
        model=SMART_MODEL,
        input=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "filename": filename,
                        "file_data": f"data:application/pdf;base64,{pdf_data}",
                    },
                ],
            },
        ],
        text={"format": {"type": "json_schema", "name": "SpreadsheetResponse", "schema": schema}},
    )

    # Track the request
    duration_ms = int((time.time() - start_time) * 1000)
    usage = getattr(response, "usage", None)
    if usage:
        await track_ai_request(
            function_name="generate_spreadsheet_helper",
            model=SMART_MODEL,
            user_id=user_id,
            job_id=job_id,
            prompt_tokens=getattr(usage, "input_tokens", 0),
            completion_tokens=getattr(usage, "output_tokens", 0),
            duration_ms=duration_ms,
        )

    value = response.output_text
    if not value:
        raise ValueError("No output received from LLM")
    value = StudyTable.model_validate_json(value)
    return value


@ai_checkpoint
async def generate_vignette_questions(
    filename: str,
    custom_prompt: str | None = None,
    user_id: int | None = None,
    job_id: int | None = None,
) -> VignetteQuestions:
    """Generate 2-3 step-style vignette multiple choice questions for each learning objective.

    Args:
        filename: Path to the PDF file.
        custom_prompt: Optional custom prompt to use instead of default.
        user_id: User ID for tracking.
        job_id: Job ID for tracking.
    """
    start_time = time.time()
    prompt = custom_prompt or read_prompt("generate_vignette_questions")

    # Read and encode the PDF
    with open(filename, "rb") as pdf_file:
        pdf_data = base64.b64encode(pdf_file.read()).decode("utf-8")

    response = await client.responses.parse(
        model=SMART_MODEL,
        input=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "filename": filename,
                        "file_data": f"data:application/pdf;base64,{pdf_data}",
                    }
                ],
            },
        ],
        text_format=VignetteQuestions,
    )

    # Track the request
    duration_ms = int((time.time() - start_time) * 1000)
    usage = getattr(response, "usage", None)
    if usage:
        await track_ai_request(
            function_name="generate_vignette_questions",
            model=SMART_MODEL,
            user_id=user_id,
            job_id=job_id,
            prompt_tokens=getattr(usage, "input_tokens", 0),
            completion_tokens=getattr(usage, "output_tokens", 0),
            duration_ms=duration_ms,
        )

    value = response.output_text
    if not value:
        raise ValueError("No output received from LLM")
    value = VignetteQuestions.model_validate_json(value)
    return value


@ai_checkpoint
async def generate_mindmap(
    filename: str,
    custom_prompt: str | None = None,
    user_id: int | None = None,
    job_id: int | None = None,
) -> list[tuple[str, str]]:
    """Generate one or more Mermaid mindmap diagrams from a PDF file.

    Args:
        filename: Path to the PDF file.
        custom_prompt: Optional custom prompt to use instead of default.
        user_id: User ID for tracking.
        job_id: Job ID for tracking.

    Returns:
        List of tuples containing (title, mermaid_code) for each mindmap.
    """
    start_time = time.time()
    prompt = custom_prompt or read_prompt("generate_mindmap")

    # Read and encode the PDF
    with open(filename, "rb") as pdf_file:
        pdf_data = base64.b64encode(pdf_file.read()).decode("utf-8")

    response = await client.responses.parse(
        model=SMART_MODEL,
        input=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "filename": filename,
                        "file_data": f"data:application/pdf;base64,{pdf_data}",
                    }
                ],
            },
        ],
        text_format=MindmapResponse,
    )

    # Track the request
    duration_ms = int((time.time() - start_time) * 1000)
    usage = getattr(response, "usage", None)
    if usage:
        await track_ai_request(
            function_name="generate_mindmap",
            model=SMART_MODEL,
            user_id=user_id,
            job_id=job_id,
            prompt_tokens=getattr(usage, "input_tokens", 0),
            completion_tokens=getattr(usage, "output_tokens", 0),
            duration_ms=duration_ms,
        )

    value = response.output_text
    if not value:
        raise ValueError("No output received from LLM")
    parsed = MindmapResponse.model_validate_json(value)
    return [(m.title, m.mermaid_code) for m in parsed.mindmaps]
