import base64
import hashlib
import os
from collections import namedtuple
from io import BytesIO

import requests
from chatlas import ChatOpenAI, content_image_file, content_pdf_file
from openai import AsyncOpenAI
from pydub import AudioSegment

from .schemas import StudyTable, VignetteQuestions

Caption = namedtuple("Caption", ("text", "timestamp"))
Slide = namedtuple("Slide", ("image", "caption", "extra"))
Progress = namedtuple("Progress", ("stage", "complete", "total"))

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
    prompt = f"""Clean up this voice transcription. Remove any filler words, typos and correct any words that is not in the context. If I correct myself, only include the corrected version. Only output the cleaned transcript, do not say anything like 'Here is the cleaned up transcript' in the beginning. Transcript start after the '---' line.
---
{content}"""

    chat = ChatOpenAI(api_key=key, model=FAST_MODEL)
    response = await chat.chat_async(prompt, echo="none")
    return await response.get_content()


async def gen_keypoints(content: str, slide_path: str) -> str:
    prompt = "Generate a bulleted list of key points from a voice transcription and attached slide. Only output the key points, do not say anything like 'Here are some key points' in the beginning"

    chat = ChatOpenAI(api_key=key, model=SMART_MODEL, system_prompt=prompt)
    response = await chat.chat_async(
        f"Transcript:\n\n{content}",
        content_image_file(slide_path, resize="high"),
        echo="none",
    )
    return await response.get_content()


async def generate_title(html: str) -> str:
    prompt = f"From the HTML content, generate an appropriate title for the file. Only output the title, do not say anything like 'Here is the title' in the beginning. Do not include any HTML tags or a file extension.\nHTML:\n\n{html}"

    chat = ChatOpenAI(api_key=key, model=FAST_MODEL)
    response = await chat.chat_async(prompt, echo="none")
    return await response.get_content()


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


async def generate_spreadsheet_helper(filename: str) -> StudyTable:
    """Generate a study table from a PDF file."""
    prompt = read_file("prompt.md")

    chat = ChatOpenAI(api_key=key, model=SMART_MODEL, system_prompt=prompt)

    result = await chat.chat_structured_async(
        content_pdf_file(filename),
        data_model=StudyTable,
    )

    return result


async def generate_vignette_questions(filename: str) -> VignetteQuestions:
    """Generate 2-3 step-style vignette multiple choice questions for each learning objective."""
    prompt = """You are assisting medical students by creating Step 1-style vignette questions based on lecture content.

Instructions:

1. First, identify ALL learning objectives from the lecture PDF. These are typically listed at the beginning of the lecture or explicitly stated as "Learning Objectives" or "By the end of this lecture, you should be able to..."

2. For EACH learning objective identified, create 2-3 multiple choice questions in classic USMLE Step 1 vignette style.

Vignette Question Format:
- Start with a clinical scenario: patient age, sex, presenting complaint, relevant history
- Include pertinent physical exam findings, lab values, or imaging results
- Ask a specific question that tests understanding of the learning objective
- Provide 5 answer choices (A-E), with ONE correct answer
- Include a brief explanation of why the correct answer is right and why the distractors are wrong

Example Vignette Question:
Learning Objective: Understand the pathophysiology of Primary Biliary Cholangitis

Question 1:
A 48-year-old woman presents to her physician with a 6-month history of progressive fatigue and generalized itching that is worse at night. Physical examination reveals mild scleral icterus and yellowish plaques around her eyelids bilaterally. Laboratory studies show:
- Alkaline phosphatase: 450 U/L (normal: 30-120 U/L)
- Total bilirubin: 2.1 mg/dL (normal: 0.1-1.2 mg/dL)
- Anti-mitochondrial antibody: Positive

Which of the following best describes the underlying pathophysiology of this patient's condition?

A) Autoimmune destruction of hepatocytes leading to centrilobular necrosis
B) Immune-mediated destruction of intrahepatic bile ducts causing cholestasis
C) Viral infection causing acute hepatocellular injury
D) Obstruction of the common bile duct by gallstones
E) Drug-induced hepatotoxicity affecting zone 3 hepatocytes

Correct Answer: B

Explanation: This patient has Primary Biliary Cholangitis (PBC), characterized by autoimmune destruction of small intrahepatic bile ducts. The positive anti-mitochondrial antibody (AMA) is virtually diagnostic. The destruction leads to cholestasis, causing the elevated ALP, pruritus (from bile salt deposition in skin), and xanthelasma (cholesterol deposits from impaired bile excretion). Option A describes autoimmune hepatitis. Option C would show different serologic markers. Option D would show dilated bile ducts on imaging. Option E would have a medication history.

Formatting:
- Use **Markdown bold** for key terms, diseases, lab values, and important clinical findings
- Organize by Learning Objective
- Number questions sequentially within each learning objective
- Include difficulty level (Easy/Medium/Hard) for each question"""

    chat = ChatOpenAI(api_key=key, model=SMART_MODEL, system_prompt=prompt)

    result = await chat.chat_structured_async(
        content_pdf_file(filename),
        data_model=VignetteQuestions,
    )

    return result
