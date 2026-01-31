#!/usr/bin/env python3
"""
Test script for the match_frames logic.

Uses the same frame comparison algorithm as the production pipeline.

Usage:
    python scripts/test_match_frames.py <video_file> [output_folder] [--threshold 0.92] [--scale 0.5]

Examples:
    python scripts/test_match_frames.py video.mp4
    python scripts/test_match_frames.py video.mp4 ./frames --threshold 0.90
    python scripts/test_match_frames.py video.mp4 ./frames --scale 0.25
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import cv2

from core.tasks import (
    FRAME_SCALE_FACTOR,
    FRAME_SIMILARITY_THRESHOLD,
    compare_frames_edges,
    preprocess_frame_for_comparison,
)


def match_frames(
    video_path: str,
    output_folder: str,
    threshold: float = FRAME_SIMILARITY_THRESHOLD,
    scale_factor: float = FRAME_SCALE_FACTOR,
    sample_interval_ms: int = 1000,
) -> list[dict]:
    """
    Extract unique frames from a video based on edge similarity.

    Args:
        video_path: Path to the video file
        output_folder: Folder to save extracted frames
        threshold: Similarity threshold (0-1). Lower = more sensitive to changes
        scale_factor: Scale factor for comparison (0.25-1.0). Lower = faster
        sample_interval_ms: Interval between frame samples in milliseconds

    Returns:
        List of dicts with frame info: {"path": str, "timestamp_ms": int, "score": float}
    """
    os.makedirs(output_folder, exist_ok=True)

    stream = cv2.VideoCapture(video_path)
    if not stream.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    # Get video info
    fps = stream.get(cv2.CAP_PROP_FPS)
    total_frames = int(stream.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_ms = int((total_frames / fps) * 1000) if fps > 0 else 0

    print(f"Video: {video_path}")
    print(f"  FPS: {fps:.2f}")
    print(f"  Total frames: {total_frames}")
    print(f"  Duration: {duration_ms / 1000:.1f}s")
    print(f"  Threshold: {threshold}")
    print(f"  Scale factor: {scale_factor}")
    print(f"  Sample interval: {sample_interval_ms}ms")
    print(f"  Algorithm: Edge-based (Canny + correlation)")
    print()

    last_frame = None
    last_frame_gs = None
    extracted_frames = []
    frame_count = 0
    start_time = time.time()

    # Sample at regular intervals
    current_ms = 0
    while current_ms < duration_ms:
        stream.set(cv2.CAP_PROP_POS_MSEC, current_ms)
        ret, frame = stream.read()

        if not ret:
            current_ms += sample_interval_ms
            continue

        # Use the same preprocessing as production
        frame_gs = preprocess_frame_for_comparison(frame, scale_factor)

        frame_count += 1

        if last_frame is None:
            # First frame - always save
            frame_path = os.path.join(output_folder, f"frame_{len(extracted_frames):04d}.jpg")
            cv2.imwrite(frame_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            extracted_frames.append(
                {
                    "path": frame_path,
                    "timestamp_ms": current_ms,
                    "score": 1.0,
                }
            )
            last_frame = frame
            last_frame_gs = frame_gs
            print(f"  Frame {len(extracted_frames):4d} @ {current_ms / 1000:6.1f}s (first frame)")
        else:
            # Use the same comparison function as production
            score = compare_frames_edges(last_frame_gs, frame_gs)

            if score < threshold:
                # Significant change detected - save frame
                frame_path = os.path.join(output_folder, f"frame_{len(extracted_frames):04d}.jpg")
                cv2.imwrite(frame_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                extracted_frames.append(
                    {
                        "path": frame_path,
                        "timestamp_ms": current_ms,
                        "score": score,
                    }
                )
                last_frame = frame
                last_frame_gs = frame_gs
                print(
                    f"  Frame {len(extracted_frames):4d} @ {current_ms / 1000:6.1f}s (score: {score:.3f})"
                )

        current_ms += sample_interval_ms

    stream.release()

    elapsed = time.time() - start_time
    print()
    print(
        f"Processed {frame_count} samples in {elapsed:.2f}s ({frame_count / elapsed:.1f} samples/sec)"
    )
    print(f"Extracted {len(extracted_frames)} unique frames to: {output_folder}")

    return extracted_frames


def main():
    parser = argparse.ArgumentParser(
        description="Extract unique frames from a video using edge-based comparison",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s video.mp4
  %(prog)s video.mp4 ./output_frames
  %(prog)s video.mp4 --threshold 0.90 --scale 0.25
  %(prog)s video.mp4 --interval 500
        """,
    )
    parser.add_argument("video", help="Path to the video file")
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Output folder for frames (default: ./frames_<video_name>)",
    )
    parser.add_argument(
        "--threshold",
        "-t",
        type=float,
        default=FRAME_SIMILARITY_THRESHOLD,
        help=f"Similarity threshold 0-1 (default: {FRAME_SIMILARITY_THRESHOLD}). Lower = more frames extracted",
    )
    parser.add_argument(
        "--scale",
        "-s",
        type=float,
        default=FRAME_SCALE_FACTOR,
        help=f"Scale factor for comparison 0.1-1.0 (default: {FRAME_SCALE_FACTOR}). Lower = faster",
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=1000,
        help="Sample interval in milliseconds (default: 1000)",
    )

    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f"Error: Video file not found: {args.video}", file=sys.stderr)
        sys.exit(1)

    # Default output folder based on video name
    if args.output is None:
        video_name = Path(args.video).stem
        args.output = f"./frames_{video_name}"

    try:
        frames = match_frames(
            video_path=args.video,
            output_folder=args.output,
            threshold=args.threshold,
            scale_factor=args.scale,
            sample_interval_ms=args.interval,
        )

        # Write a summary file
        summary_path = os.path.join(args.output, "summary.txt")
        with open(summary_path, "w") as f:
            f.write(f"Video: {args.video}\n")
            f.write(f"Algorithm: Edge-based (Canny + correlation)\n")
            f.write(f"Threshold: {args.threshold}\n")
            f.write(f"Scale: {args.scale}\n")
            f.write(f"Interval: {args.interval}ms\n")
            f.write(f"Frames extracted: {len(frames)}\n\n")
            for frame in frames:
                f.write(
                    f"{frame['timestamp_ms']:8d}ms  score={frame['score']:.3f}  {frame['path']}\n"
                )

        print(f"\nSummary written to: {summary_path}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
