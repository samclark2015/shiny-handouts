import base64
import hashlib
import json
import mimetypes
import os
from collections import namedtuple
from io import BytesIO

import requests
from chatlas import ChatOpenAI, content_pdf_file
from openai import AsyncOpenAI
from pydub import AudioSegment

Caption = namedtuple("Caption", ("text", "timestamp"))
Slide = namedtuple("Slide", ("image", "caption", "extra"))
Progress = namedtuple("Progress", ("stage", "complete", "total"))

FAST_MODEL = "gpt-5-nano"
SMART_MODEL = "gpt-5-nano"

key = os.environ["OPENAI_API_KEY"]

# client = ollama.AsyncClient()
client = AsyncOpenAI(api_key=key)


async def generate_captions(video_path: str) -> list[Caption]:
    video: AudioSegment = AudioSegment.from_file(video_path, format="mp4")
    audio: AudioSegment = (
        video.set_channels(1).set_frame_rate(16000).set_sample_width(2)
    )

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


def encode_image(image_path: str):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


async def clean_transcript(content: str) -> str:
    prompt = f"""Clean up this voice transcription. Remove any filler words, typos and correct any words that is not in the context. If I correct myself, only include the corrected version. Only output the cleaned transcript, do not say anything like 'Here is the cleaned up transcript' in the beginning. Transcript start after the '---' line.
---
{content}"""

    # resp = ollama.chat(model, [
    #     ollama.Message(role="user", content=prompt)
    # ])
    resp = await client.chat.completions.create(
        model=FAST_MODEL, messages=[{"role": "user", "content": prompt}]
    )

    # return resp["message"]["content"]
    # return resp["response"]
    return resp.choices[0].message.content or ""


async def gen_keypoints(content: str, slide_path: str) -> str:
    prompt = "Generate a bulleted list of key points from a voice transcription and attached slide. Only output the key points, do not say anything like 'Here are some key points' in the beginning"

    mimetype = mimetypes.guess_type(slide_path)
    slide_data = encode_image(slide_path)
    # resp = ollama.chat(model, [
    #     ollama.Message(role="user", content=prompt)
    # ])
    # resp = await client.generate(model, prompt=prompt)
    resp = await client.chat.completions.create(
        model=SMART_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Transcript:\n\n{content}"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mimetype};base64,{slide_data}"},
                    },
                ],
            },
        ],
    )
    # return resp["message"]["content"]
    return resp.choices[0].message.content or ""
    # return resp["response"]


async def generate_title(html: str) -> str:
    resp = await client.chat.completions.create(
        model=FAST_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"From the HTML content, generate an appropriate title for the fil. Only output the title, do not say anything like 'Here is the title' in the beginning. Do not include any HTML tags or a file extension.\nHTML:\n\n{html}",
                    },
                ],
            }
        ],
    )
    return resp.choices[0].message.content or ""


def get_file_hash(filename, algorithm="sha256", block_size=65536):
    """
    Calculates the hash of a file using the specified algorithm.

    Args:
        filename (str): The path to the file.
        algorithm (str): The hashing algorithm to use (e.g., 'md5', 'sha256').
        block_size (int): The block size for reading the file.

    Returns:
        str: The hexadecimal representation of the hash.
    """
    try:
        hasher = hashlib.new(algorithm)
    except ValueError:
        raise ValueError(
            f"Invalid algorithm: {algorithm}. Supported algorithms are: {hashlib.algorithms_available}"
        )

    with open(filename, "rb") as file:
        while True:
            chunk = file.read(block_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def fetch(base: str, cookie: str, url: str, params: dict[str, str] = {}):
    return requests.get(
        f"{base}/{url}", cookies={".ASPXAUTH": cookie}, params=params
    ).json()


def read_file(filename: str) -> str:
    with open(filename, "r", encoding="utf-8") as f:
        return f.read()


async def generate_spreadsheet_helper(filename: str) -> str:
    prompt = read_file("prompt.md")
    schema = json.load(open("schema.json", "r", encoding="utf-8"))

    client = ChatOpenAI(api_key=key, model=SMART_MODEL, system_prompt=prompt)

    response = client.chat(
        content_pdf_file(filename),
        echo="none",
        stream=False,
        kwargs={
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "spreadsheet_schema",
                    "schema": schema,
                }
            }
        },
    )

    data = response.get_content()
    return data
