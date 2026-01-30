import os
from io import BytesIO

from chatlas import ChatOpenAI, content_image_file, content_pdf_file
from openai import AsyncOpenAI
from pydub import AudioSegment

from .helpers import Caption, read_prompt
from .schemas import StudyTable, VignetteQuestions

FAST_MODEL = "gpt-4.1-nano"
SMART_MODEL = "gpt-5-mini"

key = os.environ["OPENAI_API_KEY"]

# OpenAI client kept only for audio transcription (Whisper)
whisper_client = AsyncOpenAI(api_key=key)


async def generate_captions(video_path: str) -> list[Caption]:
    video: AudioSegment = AudioSegment.from_file(video_path, format="mp4")
    audio: AudioSegment = (
        video.set_channels(1).set_frame_rate(16000).set_sample_width(2)
    )

    output = BytesIO()
    audio.export(output, format="mp3")

    output.seek(0)
    output.name = "audio.mp3"
    resp = await whisper_client.audio.transcriptions.create(
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


async def clean_transcript(content: str) -> str:
    prompt = read_prompt("clean_transcript")

    chat = ChatOpenAI(api_key=key, model=FAST_MODEL, system_prompt=prompt)
    response = await chat.chat_async(content, echo="none")
    return await response.get_content()


async def gen_keypoints(content: str, slide_path: str) -> str:
    prompt = read_prompt("gen_keypoints")

    chat = ChatOpenAI(api_key=key, model=SMART_MODEL, system_prompt=prompt)
    response = await chat.chat_async(
        content,
        content_image_file(slide_path, resize="high"),
        echo="none",
    )
    return await response.get_content()


async def generate_title(html: str) -> str:
    prompt = read_prompt("generate_title")
    full_prompt = f"{prompt}\nHTML:\n\n{html}"

    chat = ChatOpenAI(api_key=key, model=FAST_MODEL)
    response = await chat.chat_async(full_prompt, echo="none")
    return await response.get_content()


def _build_column_prompt_section(columns: list[dict] | None) -> str:
    """Build the column configuration section for the spreadsheet prompt."""
    if not columns:
        return ""

    column_lines = ["Column headers for each disease:", ""]
    for col in columns:
        name = col.get("name", "")
        description = col.get("description", "")
        if name:
            column_lines.append(f"- {name}: {description}" if description else f"- {name}")

    return "\n".join(column_lines)


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
    if custom_prompt:
        prompt = custom_prompt
        # If custom columns are provided, append column instructions
        if custom_columns:
            prompt += "\n\n" + _build_column_prompt_section(custom_columns)
    else:
        prompt = read_prompt("generate_spreadsheet")

    chat = ChatOpenAI(api_key=key, model=SMART_MODEL, system_prompt=prompt)

    result = await chat.chat_structured_async(
        content_pdf_file(filename),
        data_model=StudyTable,
    )

    return result


async def generate_vignette_questions(
    filename: str,
    custom_prompt: str | None = None,
) -> VignetteQuestions:
    """Generate 2-3 step-style vignette multiple choice questions for each learning objective.

    Args:
        filename: Path to the PDF file.
        custom_prompt: Optional custom prompt to use instead of default.
    """
    if custom_prompt:
        prompt = custom_prompt
    else:
        prompt = read_prompt("generate_vignette_questions")

    chat = ChatOpenAI(api_key=key, model=SMART_MODEL, system_prompt=prompt)

    result = await chat.chat_structured_async(
        content_pdf_file(filename),
        data_model=VignetteQuestions,
    )

    return result
