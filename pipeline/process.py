import asyncio
import os
import subprocess
import tempfile
import urllib.request
from collections import namedtuple
from dataclasses import dataclass
from typing import Callable, cast
from urllib.parse import urljoin
from uuid import uuid4

import cv2
import m3u8
import skimage as ski
from jinja2 import Environment, FileSystemLoader, select_autoescape
from xhtml2pdf import pisa

from pipeline.helpers import (
    Caption,
    Slide,
    clean_transcript,
    fetch,
    generate_captions,
    generate_title,
)

from .pipeline import Pipeline, PipelineFailure, Progress

in_dir = os.path.join("data", "input")
out_dir = os.path.join("data", "output")

PanoptoInput = namedtuple("PanoptoInput", ["base", "cookie", "delivery_id"])

ProcessingInput = str | PanoptoInput

ENABLE_AI = True  # Set to False to disable AI processing


@dataclass
class ProcessingContext:
    """Context object that flows through the pipeline stages."""

    pipeline: Pipeline
    source_id: str
    source: str | PanoptoInput
    use_ai: bool
    captions: list[Caption] | None = None
    slides: list[Slide] | None = None

    @property
    def video_path(self) -> str:
        if isinstance(self.source, str) and os.path.exists(self.source):
            return self.source
        return os.path.join(in_dir, f"video_{self.source_id}.mp4")


# Utility functions for video download
def _is_m3u8_url(url: str) -> bool:
    """Check if a URL points to an M3U8 file."""
    return url.endswith(".m3u8") or "m3u8" in url


def _download_m3u8_stream(ctx: ProcessingContext, video_url: str) -> None:
    """Download and combine M3U8 stream segments into a single video file."""
    ctx.pipeline.report_progress("Parsing playlist")

    try:
        # Parse the m3u8 playlist
        playlist = m3u8.load(video_url)

        if playlist.is_variant:
            # Select the highest quality stream or first available
            if playlist.playlists:
                # Sort by bandwidth (highest first) and select the best quality
                best_playlist = min(
                    playlist.playlists,
                    key=lambda p: p.stream_info.bandwidth
                    if p.stream_info.bandwidth
                    else 0,
                )
                stream_url = urljoin(video_url, best_playlist.uri)
                playlist = m3u8.load(stream_url)
            else:
                raise PipelineFailure("No streams found in variant playlist")

        # Download and combine segments
        segments = playlist.segments
        total_segments = len(segments)

        if total_segments == 0:
            raise PipelineFailure("No segments found in playlist")

        # Create a temporary directory for segments
        with tempfile.TemporaryDirectory() as temp_dir:
            segment_files = []

            # Download each segment with retry logic
            for i, segment in enumerate(segments):
                segment_url = urljoin(playlist.base_uri or video_url, segment.uri)
                segment_path = os.path.join(temp_dir, f"segment_{i:04d}.ts")

                # Retry download up to 3 times
                for attempt in range(3):
                    try:
                        urllib.request.urlretrieve(segment_url, segment_path)
                        # Verify the segment was downloaded completely
                        if os.path.getsize(segment_path) > 0:
                            break
                    except Exception as e:
                        if attempt == 2:  # Last attempt
                            raise ValueError(
                                f"Failed to download segment {i} after 3 attempts: {e}"
                            )
                        continue

                segment_files.append(segment_path)

                # Update progress
                ctx.pipeline.report_progress(
                    "Downloading video segments", (i + 1) / total_segments
                )

            # Use ffmpeg to properly concatenate segments instead of binary concatenation
            ctx.pipeline.report_progress("Combining segments")

            # Create a file list for ffmpeg
            concat_file = os.path.join(temp_dir, "segments.txt")
            with open(concat_file, "w") as f:
                for segment_file in segment_files:
                    f.write(f"file '{segment_file}'\n")

            # Use ffmpeg to concatenate properly
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    concat_file,
                    "-c",
                    "copy",
                    "-y",
                    ctx.video_path,
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                # Fallback to binary concatenation if ffmpeg fails
                with open(ctx.video_path, "wb") as outfile:
                    for segment_file in segment_files:
                        with open(segment_file, "rb") as infile:
                            outfile.write(infile.read())

    except urllib.request.HTTPError as e:
        raise PipelineFailure(
            f"HTTP Error while downloading m3u8 stream: {str(e)} @ {e.url}"
        )
    except Exception as e:
        raise PipelineFailure(f"Failed to download m3u8 stream: {str(e)}")


def _download_regular_video(
    ctx: ProcessingContext, video_url: str, use_range_header: bool = True
) -> ProcessingContext:
    """Download a regular video file."""
    if use_range_header:
        opener = urllib.request.build_opener()
        opener.addheaders = [("Range", "bytes=0-")]
        urllib.request.install_opener(opener)

    urllib.request.urlretrieve(
        video_url,
        ctx.video_path,
        reporthook=lambda count, bs, ts: ctx.pipeline.report_progress(
            "Downloading", count * bs / ts
        ),
    )
    return ctx


# Panopto-specific functions
def _get_delivery_info(
    base: str, cookie: str, delivery_id: str, captions: bool = False
):
    """Get delivery info from Panopto."""
    url = "Panopto/Pages/Viewer/DeliveryInfo.aspx"
    data = fetch(
        base,
        cookie,
        url,
        {
            "deliveryId": delivery_id,
            "responseType": "json",
            "getCaptions": "true" if captions else "false",
            "language": "0",
        },
    )
    return data


def _download_panopto_video(ctx: ProcessingContext) -> ProcessingContext:
    """Download video from Panopto if it doesn't exist."""
    # Get the video URL from Panopto
    panopto = cast(PanoptoInput, ctx.source)
    delivery_info = _get_delivery_info(
        panopto.base, panopto.cookie, panopto.delivery_id
    )
    vidurl = delivery_info["Delivery"]["PodcastStreams"][0]["StreamUrl"]

    # Check if the URL points to an m3u8 file
    if _is_m3u8_url(vidurl):
        # Use m3u8 library to parse and download stream
        _download_m3u8_stream(ctx, vidurl)
    else:
        # Regular video file download
        _download_regular_video(ctx, vidurl, False)

    print("Downloaded video to", ctx.video_path)
    return ctx


# Pipeline stage functions


def generate_context(pipeline: Pipeline, input: ProcessingInput) -> ProcessingContext:
    """Generate processing context from input."""
    source_id = (
        input.delivery_id if isinstance(input, PanoptoInput) else str(hash(input))
    )
    return ProcessingContext(
        pipeline,
        source_id,
        input,
        ENABLE_AI,
    )


def download_video(pipeline: Pipeline, ctx: ProcessingContext) -> ProcessingContext:
    """Download video if it doesn't exist."""
    if (
        isinstance(ctx.source, str)
        and os.path.exists(ctx.source)
        and ctx.source == ctx.video_path
    ):
        return ctx

    if not os.path.exists(ctx.video_path):
        # Check if the URL points to an m3u8 file
        if isinstance(ctx.source, PanoptoInput):
            return _download_panopto_video(ctx)
        else:
            return _download_regular_video(ctx, ctx.source)
    return ctx


async def extract_captions(
    pipeline: Pipeline, ctx: ProcessingContext
) -> ProcessingContext:
    """Extract captions from the video."""
    ctx.pipeline.report_progress("Transcribing")
    ctx.captions = await generate_captions(ctx.video_path)
    return ctx


def match_frames(pipeline: Pipeline, ctx: ProcessingContext) -> ProcessingContext:
    """Match frames to captions based on structural similarity."""
    if not ctx.captions:
        ctx.slides = []
        return ctx

    last_frame = None
    last_frame_gs = None
    cum_captions = []

    pairs: list[Slide] = []

    stream = cv2.VideoCapture()
    stream.open(ctx.video_path)

    frame_path = os.path.join("data", "frames", ctx.source_id)
    os.makedirs(frame_path, exist_ok=True)

    for idx, cap in enumerate(ctx.captions):
        stream.set(cv2.CAP_PROP_POS_MSEC, cap.timestamp * 1_000 + 500)
        ret, frame = stream.read()
        if not ret:
            raise ValueError("Could not read frame")

        frame_gs = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if last_frame is None:
            last_frame = frame
            last_frame_gs = frame_gs
            cum_captions.append(cap.text)
            continue

        similarity_result = ski.metrics.structural_similarity(
            last_frame_gs, frame_gs, full=False
        )
        # Handle both single score and tuple return types
        score = (
            similarity_result
            if isinstance(similarity_result, (int, float))
            else similarity_result[0]
        )

        if score < 0.925 or (idx + 1) == len(ctx.captions):
            cap_full = " ".join(cum_captions)
            image_path = os.path.join(frame_path, f"{uuid4()}.png")
            cv2.imwrite(image_path, last_frame)

            pairs.append(Slide(image_path, cap_full, None))
            last_frame = frame
            last_frame_gs = frame_gs
            cum_captions.clear()
            ctx.pipeline.report_progress(
                "Matching Slides", (idx + 1) / len(ctx.captions)
            )
        cum_captions.append(cap.text)

    stream.release()
    ctx.slides = pairs
    return ctx


async def transform_slides_with_ai(
    pipeline: Pipeline, ctx: ProcessingContext
) -> ProcessingContext:
    """Apply AI transformation to slides if enabled."""
    if not ctx.use_ai or not ctx.slides:
        return ctx

    async def transform_slide(slide: Slide) -> Slide:
        """Transform a single slide using AI."""
        cleaned = await clean_transcript(slide.caption)
        keypoints = None
        # cleaned, keypoints = await asyncio.gather(clean_transcript(slide.caption), gen_keypoints(slide.caption, slide.image))
        return Slide(slide.image, cleaned, keypoints)

    output: list[Slide] = []
    for idx, slide in enumerate(ctx.slides):
        ctx.pipeline.report_progress(
            "Cleaning Transcript with AI", (idx + 1) / len(ctx.slides)
        )
        output.append(await transform_slide(slide))
    ctx.slides = output
    return ctx


def generate_pdf_output(ctx: ProcessingContext, html: str, path: str) -> None:
    """Generate PDF from HTML."""
    with open(path, "wb") as f:
        pisa_status = pisa.CreatePDF(html, dest=f)
        # Check for errors if available
        if hasattr(pisa_status, "err") and getattr(pisa_status, "err", None):
            raise ValueError("Error generating PDF")


async def generate_output(pipeline: Pipeline, ctx: ProcessingContext) -> str:
    """Generate the final PDF output."""
    pipeline.report_progress("Generating PDF", 0)
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "templates"
    )
    env = Environment(
        loader=FileSystemLoader(template_path), autoescape=select_autoescape()
    )
    template = env.get_template("template.html")

    html = template.render(pairs=ctx.slides)

    title = await generate_title(html)
    path = os.path.join(out_dir, f"{title}.pdf")
    os.makedirs(out_dir, exist_ok=True)

    # Run PDF generation in executor since it's CPU-bound
    await asyncio.get_event_loop().run_in_executor(
        None, generate_pdf_output, ctx, html, path
    )
    pipeline.report_progress("Generating PDF", 1.0)

    return path


def create_pipeline(
    callback: Callable[[Pipeline, Progress], None],
) -> Pipeline[ProcessingInput, str]:
    pipeline = (
        Pipeline[ProcessingInput](callback)
        .add_stage(generate_context)
        .add_stage(download_video)
        .add_stage(extract_captions)
        .add_stage(match_frames)
        .add_stage(transform_slides_with_ai)
        .add_stage(generate_output)
    )
    return pipeline
