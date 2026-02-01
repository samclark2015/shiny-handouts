"""
Video download utilities for various sources.
"""

import asyncio
import hashlib
import os
import subprocess
import tempfile
import urllib.request
from urllib.parse import urljoin

import aiohttp
import m3u8

from pipeline.helpers import fetch

from .progress import update_job_progress


async def hash_file(file_path: str) -> str:
    """Generate SHA256 hash of file contents.

    Args:
        file_path: Path to the file to hash

    Returns:
        Hexadecimal hash string
    """

    def _hash_sync():
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read file in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    return await asyncio.to_thread(_hash_sync)


def is_m3u8_url(url: str) -> bool:
    """Check if a URL points to an M3U8 file."""
    return url.endswith(".m3u8") or "m3u8" in url


async def download_regular_video(
    job_id: int, stage_name: str, video_url: str, video_path: str
) -> None:
    """Download a regular video file."""
    await update_job_progress(job_id, stage_name, 0.1, "Starting download")

    async with aiohttp.ClientSession() as session, session.get(video_url) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        downloaded = 0
        last_reported_percent = -1

        with open(video_path, "wb") as f:
            async for chunk in response.content.iter_chunked(8192):
                f.write(chunk)
                downloaded += len(chunk)

                if total > 0:
                    progress = downloaded / total
                    # Scale to stage range: 0.1 to 0.9
                    scaled_progress = 0.1 + (progress * 0.8)
                    # Report every 5% to avoid too many updates
                    current_percent = int(progress * 20)
                    if current_percent > last_reported_percent:
                        await update_job_progress(
                            job_id,
                            stage_name,
                            scaled_progress,
                            f"Downloading video ({int(progress * 100)}%)",
                        )
                        last_reported_percent = current_percent

    await update_job_progress(job_id, stage_name, 0.9, "Download complete")


async def download_m3u8_stream(
    job_id: int, stage_name: str, video_url: str, video_path: str
) -> None:
    """Download and combine M3U8 stream segments."""
    await update_job_progress(job_id, stage_name, 0.1, "Parsing playlist")

    playlist = await asyncio.to_thread(m3u8.load, video_url)

    if playlist.is_variant:
        if playlist.playlists:
            best_playlist = min(
                playlist.playlists,
                key=lambda p: p.stream_info.bandwidth if p.stream_info.bandwidth else 0,
            )
            stream_url = urljoin(video_url, best_playlist.uri)
            playlist = await asyncio.to_thread(m3u8.load, stream_url)
        else:
            raise ValueError("No streams found in variant playlist")

    segments = playlist.segments
    total_segments = len(segments)

    if total_segments == 0:
        raise ValueError("No segments found in playlist")

    with tempfile.TemporaryDirectory() as temp_dir:
        segment_files = []

        for i, segment in enumerate(segments):
            segment_url = urljoin(playlist.base_uri or video_url, segment.uri)
            segment_path = os.path.join(temp_dir, f"segment_{i:04d}.ts")

            for attempt in range(3):
                try:
                    await asyncio.to_thread(urllib.request.urlretrieve, segment_url, segment_path)
                    if os.path.getsize(segment_path) > 0:
                        break
                except Exception as e:
                    if attempt == 2:
                        raise ValueError(f"Failed to download segment {i}: {e}") from e

            segment_files.append(segment_path)
            progress = (i + 1) / total_segments * 0.8
            await update_job_progress(job_id, stage_name, progress, "Downloading segments")

        await update_job_progress(job_id, stage_name, 0.85, "Combining segments")

        concat_file = os.path.join(temp_dir, "segments.txt")
        with open(concat_file, "w") as f:
            for segment_file in segment_files:
                f.write(f"file '{segment_file}'\n")

        result = await asyncio.to_thread(
            subprocess.run,
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
                video_path,
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            with open(video_path, "wb") as outfile:
                for segment_file in segment_files:
                    with open(segment_file, "rb") as infile:
                        outfile.write(infile.read())


async def download_panopto_video(
    job_id: int, stage_name: str, panopto_data: dict, video_path: str
) -> None:
    """Download video from Panopto."""
    base = panopto_data["base"]
    cookie = panopto_data["cookie"]
    delivery_id = panopto_data["delivery_id"]

    await update_job_progress(job_id, stage_name, 0.1, "Getting Panopto info")

    delivery_info = await asyncio.to_thread(
        fetch,
        base,
        cookie,
        "Panopto/Pages/Viewer/DeliveryInfo.aspx",
        {
            "deliveryId": delivery_id,
            "responseType": "json",
            "getCaptions": "false",
            "language": "0",
        },
    )

    vidurl = delivery_info["Delivery"]["PodcastStreams"][0]["StreamUrl"]

    if is_m3u8_url(vidurl):
        await download_m3u8_stream(job_id, stage_name, vidurl, video_path)
    else:
        await download_regular_video(job_id, stage_name, vidurl, video_path)
