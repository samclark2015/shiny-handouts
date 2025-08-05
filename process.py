import asyncio
import concurrent.futures
import os
import shutil
import tempfile
import urllib.request
from typing import Callable
from urllib.parse import urljoin
from uuid import uuid4

import cv2
import m3u8
import requests
import skimage as ski
from jinja2 import Environment, FileSystemLoader, select_autoescape
from xhtml2pdf import pisa

from helpers import (
    Caption,
    Progress,
    Slide,
    clean_transcript,
    fetch,
    generate_captions,
    generate_title,
    get_file_hash,
)

out_dir = os.path.join("data", "output")


class Processor:
    def __init__(
        self,
        video_url: str,
        use_ai: bool = False,
        redo_transcription: bool = False,
        callback: Callable[[Progress], None] | None = None,
    ) -> None:
        self.video_url = video_url
        self.use_ai = use_ai
        self.redo_transcription = redo_transcription
        self.callback = callback or (lambda _: None)
        self.pool = concurrent.futures.ThreadPoolExecutor()

        if os.path.exists(video_url):
            self.delivery_id = get_file_hash(video_url)
            self.video_path = video_url
        else:
            header = requests.head(self.video_url, headers={"Range": "bytes=0-"})
            self.delivery_id = header.headers["Etag"]
            self.video_path = os.path.join("data", "input", f"{self.delivery_id}.mp4")

        os.makedirs(os.path.join("data/frames", self.delivery_id), exist_ok=True)

    def _is_m3u8_url(self, url: str) -> bool:
        """Check if a URL points to an M3U8 file."""
        return url.endswith(".m3u8") or "m3u8" in url

    def _download_m3u8_stream(self, url: str) -> None:
        """Download and combine M3U8 stream segments into a single video file."""
        self.callback(Progress("Parsing m3u8 playlist", 0, 1))

        try:
            # Parse the m3u8 playlist
            playlist = m3u8.load(url)

            if playlist.is_variant:
                # Multiple quality streams available, select the first one
                # (or you could implement quality selection logic here)
                if playlist.playlists:
                    stream_url = urljoin(url, playlist.playlists[0].uri)
                    playlist = m3u8.load(stream_url)
                else:
                    raise ValueError("No streams found in variant playlist")

            # Download and combine segments
            segments = playlist.segments
            total_segments = len(segments)

            if total_segments == 0:
                raise ValueError("No segments found in playlist")

            # Create a temporary directory for segments
            with tempfile.TemporaryDirectory() as temp_dir:
                segment_files = []

                # Download each segment
                for i, segment in enumerate(segments):
                    segment_url = urljoin(url, segment.uri)
                    segment_path = os.path.join(temp_dir, f"segment_{i:04d}.ts")

                    urllib.request.urlretrieve(segment_url, segment_path)
                    segment_files.append(segment_path)

                    # Update progress
                    self.callback(
                        Progress("Downloading m3u8 segments", i + 1, total_segments)
                    )

                # Combine segments into final video file
                self.callback(Progress("Combining segments", 0, 1))

                with open(self.video_path, "wb") as outfile:
                    for segment_file in segment_files:
                        with open(segment_file, "rb") as infile:
                            outfile.write(infile.read())

                self.callback(Progress("Combining segments", 1, 1))

        except urllib.request.HTTPError as e:
            # self.callback(Progress("Error", 1, 1))
            body = e.read().decode("utf-8")
            raise ValueError(
                f"HTTP Error while downloading m3u8 stream: {str(e)}, {body}"
            )
        except Exception as e:
            raise ValueError(f"Failed to download m3u8 stream: {str(e)}")

    def _download_regular_video(self, url: str, use_range_header: bool = True) -> None:
        """Download a regular video file."""
        if use_range_header:
            opener = urllib.request.build_opener()
            opener.addheaders = [("Range", "bytes=0-")]
            urllib.request.install_opener(opener)

        urllib.request.urlretrieve(
            url,
            self.video_path,
            reporthook=lambda count, bs, ts: self.callback(
                Progress("Downloading", count * bs, ts)
            ),
        )

    def download_video(self) -> str:
        # Check if the URL points to an m3u8 file
        if self._is_m3u8_url(self.video_url):
            # Use m3u8 library to parse and download stream
            self._download_m3u8_stream(self.video_url)
        else:
            # Regular video file download
            self._download_regular_video(self.video_url, use_range_header=True)
        return self.video_path

    async def get_captions(self) -> list[Caption]:
        # delivery_info = self.get_delivery_info(captions=True)
        # return [Caption(cap["Caption"], cap["Time"]) for cap in delivery_info]
        self.callback(Progress("Transcribing", 0.5, 1))
        return await generate_captions(self.video_path)

    def match_frames(self, captions: list[Caption]) -> list[Slide]:
        last_frame = None
        last_frame_gs = None
        cum_captions = []

        pairs: list[Slide] = []

        stream = cv2.VideoCapture()
        stream.open(self.video_path)

        for idx, cap in enumerate(captions):
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

            score, _ = ski.metrics.structural_similarity(
                last_frame_gs, frame_gs, full=True
            )

            if score < 0.925 or (idx + 1) == len(captions):
                cap_full = " ".join(cum_captions)
                image_path = os.path.join(
                    "data", "frames", self.delivery_id, f"{uuid4()}.png"
                )
                cv2.imwrite(image_path, last_frame)

                pairs.append(Slide(image_path, cap_full, None))
                last_frame = frame
                last_frame_gs = frame_gs
                cum_captions.clear()
                self.callback(Progress("Matching Slides", idx + 1, len(captions)))
            cum_captions.append(cap.text)
        return pairs

    async def write_output(self, captions: list[Slide]) -> str:
        template_path = os.path.join(os.path.dirname(__file__), "templates")
        env = Environment(
            loader=FileSystemLoader(template_path), autoescape=select_autoescape()
        )
        template = env.get_template("template.html")

        html = template.render(pairs=captions)

        title = await generate_title(html)
        path = os.path.join(out_dir, f"{title}.pdf")

        with open(path, "wb") as f:
            pisa_status = await self.run_in_threadpool(pisa.CreatePDF, html, dest=f)
            if pisa_status.err:
                raise ValueError("Error generating PDF", pisa_status)

        return path

    async def ai_transform_all(self, pairs: list[Slide]) -> list[Slide]:
        async def transform(pair: Slide):
            cleaned = await clean_transcript(pair.caption)
            keypoints = None
            # cleaned, keypoints = await asyncio.gather(clean_transcript(pair.caption), gen_keypoints(pair.caption, pair.image))
            return Slide(pair.image, cleaned, keypoints)

        output: list[Slide] = []
        for idx, pair in enumerate(pairs):
            self.callback(Progress("Cleaning Transcript with AI", idx + 1, len(pairs)))
            output.append(await transform(pair))
        return output

    async def run_in_threadpool(self, func: Callable, *args, **kwargs):
        def wrapper():
            return func(*args, **kwargs)

        return await self.loop.run_in_executor(self.pool, wrapper)

    async def generate(self) -> str:
        self.loop = asyncio.get_event_loop()
        print("Downloaded video to", self.video_path)
        if not os.path.exists(self.video_path):
            print("Downloading video...")
            await self.run_in_threadpool(self.download_video)
        caps = await self.get_captions()
        pairs = await self.run_in_threadpool(self.match_frames, caps)
        if self.use_ai:
            pairs = await self.ai_transform_all(pairs)
        filename = await self.write_output(pairs)
        # shutil.rmtree(os.path.join("data", "frames", self.delivery_id))
        return filename

    def abort(self):
        os.unlink(self.video_path)
        shutil.rmtree(os.path.join("data", "frames", self.delivery_id))


class PanoptoProcessor(Processor):
    def __init__(
        self,
        base: str,
        cookie: str,
        delivery_id: str,
        use_ai: bool = False,
        redo_transcription: bool = False,
        callback: Callable[[Progress], None] | None = None,
    ) -> None:
        self.base = base
        self.cookie = cookie
        self.delivery_id = delivery_id
        self.use_ai = use_ai
        self.redo_transcription = redo_transcription
        self.callback = callback or (lambda _: None)

        self.video_path = os.path.join("data", "input", f"{self.delivery_id}.mp4")
        self.pool = concurrent.futures.ThreadPoolExecutor()

        os.makedirs(os.path.join("data/frames", self.delivery_id), exist_ok=True)

    def get_delivery_info(self, captions: bool = False):
        url = "Panopto/Pages/Viewer/DeliveryInfo.aspx"
        data = fetch(
            self.base,
            self.cookie,
            url,
            {
                "deliveryId": self.delivery_id,
                "responseType": "json",
                "getCaptions": "true" if captions else "false",
                "language": "0",
            },
        )
        return data

    def download_video(self) -> str:
        delivery_info = self.get_delivery_info()

        vidurl = delivery_info["Delivery"]["PodcastStreams"][0]["StreamUrl"]

        # Check if the URL points to an m3u8 file
        if self._is_m3u8_url(vidurl):
            # Use m3u8 library to parse and download stream
            self._download_m3u8_stream(vidurl)
        else:
            # Regular video file download
            self._download_regular_video(vidurl, use_range_header=False)

        return self.video_path
