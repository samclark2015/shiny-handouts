import base64
import json
import logging
import os
import sys
from functools import wraps
from io import BytesIO
from pathlib import Path
from typing import cast

from openai import AsyncOpenAI
from pydub import AudioSegment

from .helpers import Caption, read_prompt
from .schemas import MindmapResponse, StudyTable, VignetteQuestions

# Import AI caching functions
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.cache import get_ai_cached_result, set_ai_cached_result

FAST_MODEL = "gpt-4.1-nano"
SMART_MODEL = "gpt-5-mini"

key = os.environ["OPENAI_API_KEY"]

# OpenAI client for all API calls
client = AsyncOpenAI(api_key=key)


def ai_checkpoint(func):
    """
    Decorator to cache AI function results to save tokens.

    This caches the result based on the function name and arguments,
    automatically skipping expensive AI calls if the same inputs are provided again.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        func_name = func.__name__
        # Try to get cached result
        cached = get_ai_cached_result(func_name, *args, **kwargs)
        if cached is not None:
            logging.info(f"[AI Checkpoint] Using cached result for {func_name}")
            return cached

        # Execute the function and cache the result
        logging.info(f"[AI Checkpoint] Executing {func_name} (no cache hit)")
        result = await func(*args, **kwargs)
        set_ai_cached_result(func_name, result, *args, **kwargs)

        return result

    return wrapper


@ai_checkpoint
async def generate_captions(video_path: str) -> list[Caption]:
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
    return captions


@ai_checkpoint
async def clean_transcript(content: str) -> str:
    prompt = read_prompt("clean_transcript")

    response = await client.responses.create(
        model=FAST_MODEL,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": content},
        ],
    )
    return response.output_text


@ai_checkpoint
async def gen_keypoints(content: str, slide_path: str) -> str:
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
                        "image_url": f"data:image/jpeg;base64,{image_data}",
                    },
                ],
            },
        ],
    )
    return response.output_text


@ai_checkpoint
async def generate_title(html: str) -> str:
    prompt = read_prompt("generate_title")
    full_prompt = f"{prompt}\nHTML:\n\n{html}"

    response = await client.responses.create(
        model=FAST_MODEL,
        input=[
            {"role": "user", "content": full_prompt},
        ],
    )
    return response.output_text


def _build_column_schema(columns: list[dict] | None) -> dict:
    """Build the column configuration section for the spreadsheet prompt."""
    if not columns:
        with open("src/prompts/default_spreadsheet_columns.json") as f:
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
) -> StudyTable:
    """Generate a study table from a PDF file.

    Args:
        filename: Path to the PDF file.
        custom_prompt: Optional custom prompt to use instead of default.
        custom_columns: Optional custom column configuration for the LLM.
    """
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

    value = response.output_text
    if not value:
        raise ValueError("No output received from LLM")
    value = StudyTable.model_validate_json(value)
    return value


@ai_checkpoint
async def generate_vignette_questions(
    filename: str,
    custom_prompt: str | None = None,
) -> VignetteQuestions:
    """Generate 2-3 step-style vignette multiple choice questions for each learning objective.

    Args:
        filename: Path to the PDF file.
        custom_prompt: Optional custom prompt to use instead of default.
    """
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

    value = response.output_text
    if not value:
        raise ValueError("No output received from LLM")
    value = VignetteQuestions.model_validate_json(value)
    return value


@ai_checkpoint
async def generate_mindmap(
    filename: str,
    custom_prompt: str | None = None,
) -> str:
    """Generate a Mermaid mindmap diagram from a PDF file.

    Args:
        filename: Path to the PDF file.
        custom_prompt: Optional custom prompt to use instead of default.

    Returns:
        Mermaid mindmap code as a string.
    """
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

    value = response.output_text
    if not value:
        raise ValueError("No output received from LLM")
    parsed = MindmapResponse.model_validate_json(value)
    return parsed.mermaid_code
