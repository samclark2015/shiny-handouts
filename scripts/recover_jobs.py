#!/usr/bin/env python
"""
Recovery script to create Job and Artifact records from existing local files.

Scans the data/output directory for generated files, groups them by lecture name,
and creates corresponding Job and Artifact database records.

Usage:
    cd src && python ../scripts/recover_jobs.py

Or with a specific user email:
    cd src && python ../scripts/recover_jobs.py --user admin@example.com
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

# Setup Django
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "handout_generator.settings")

import django

django.setup()

from django.utils import timezone

from accounts.models import User
from core.models import Artifact, ArtifactType, Job, JobStatus


# Map file extensions/patterns to artifact types
def get_artifact_type(filename: str) -> ArtifactType | None:
    """Determine artifact type from filename."""
    lower = filename.lower()

    if lower.endswith(".xlsx"):
        return ArtifactType.EXCEL_STUDY_TABLE
    elif "vignette" in lower and lower.endswith(".pdf"):
        return ArtifactType.PDF_VIGNETTE
    elif lower.endswith(".pdf"):
        return ArtifactType.PDF_HANDOUT
    elif lower.endswith(".mmd") or lower.endswith(".png") and "mindmap" in lower:
        return ArtifactType.MERMAID_MINDMAP

    return None


def extract_base_name(filename: str) -> str:
    """Extract the base lecture name from a filename."""
    # Remove extension
    name = Path(filename).stem

    # Handle .mmd files with pattern: <job name> - <artifact title>.mmd
    if filename.lower().endswith(".mmd") and " - " in name:
        # Take just the job name part (before the first " - ")
        name = name.split(" - ")[0]
        return name.strip()

    # Remove common suffixes
    suffixes_to_remove = [
        " - Vignette Questions",
        " - Vignette",
        "_vignette",
        "_mindmap",
    ]

    for suffix in suffixes_to_remove:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
        # Case insensitive check
        if name.lower().endswith(suffix.lower()):
            name = name[: -len(suffix)]

    return name.strip()


def scan_output_directory(output_dir: Path) -> dict[str, list[Path]]:
    """Scan output directory and group files by base name."""
    groups = defaultdict(list)

    for file_path in output_dir.iterdir():
        if not file_path.is_file():
            continue

        # Skip test files and non-artifact files
        if file_path.name.startswith("test"):
            continue

        artifact_type = get_artifact_type(file_path.name)
        if artifact_type is None:
            print(f"  Skipping unknown file type: {file_path.name}")
            continue

        base_name = extract_base_name(file_path.name)
        groups[base_name].append(file_path)

    return dict(groups)


def scan_input_directory(input_dir: Path) -> dict[str, Path]:
    """Scan input directory for video files."""
    videos = {}

    video_extensions = {".mp4", ".mkv", ".avi", ".mov", ".webm"}

    for file_path in input_dir.iterdir():
        if not file_path.is_file():
            continue

        if file_path.suffix.lower() in video_extensions:
            # Use stem as key for matching
            videos[file_path.stem] = file_path

    return videos


def create_job_and_artifacts(
    user: User,
    label: str,
    files: list[Path],
    video_path: Path | None = None,
    dry_run: bool = False,
) -> Job | None:
    """Create a Job and associated Artifacts."""

    if dry_run:
        print(f"\n[DRY RUN] Would create job: {label}")
        for f in files:
            artifact_type = get_artifact_type(f.name)
            print(f"  - {artifact_type}: {f.name}")
        return None

    # Check if job already exists
    existing = Job.objects.filter(label=label, user=user).first()
    if existing:
        print(f"\n[SKIP] Job already exists: {label} (ID: {existing.pk})")
        return existing

    # Create job
    job = Job.objects.create(
        user=user,
        label=label,
        title=label,
        status=JobStatus.COMPLETED,
        progress=1.0,
        current_stage="Recovered from files",
        input_type="recovered",
        input_data="{}",
        video_path=str(video_path) if video_path else None,
        created_at=timezone.now(),
        started_at=timezone.now(),
        completed_at=timezone.now(),
        enable_excel=True,
        enable_vignette=True,
        enable_mindmap=True,
    )

    print(f"\n[CREATED] Job: {label} (ID: {job.pk})")

    # Create artifacts
    for file_path in files:
        artifact_type = get_artifact_type(file_path.name)
        if artifact_type is None:
            continue

        file_size = file_path.stat().st_size if file_path.exists() else None

        artifact = Artifact.objects.create(
            job=job,
            artifact_type=artifact_type,
            file_path=file_path.name,
            file_name=file_path.name,
            file_size=file_size,
        )

        print(f"  [ARTIFACT] {artifact_type}: {file_path.name}")

    return job


def main():
    parser = argparse.ArgumentParser(
        description="Recover Job and Artifact records from local files"
    )
    parser.add_argument(
        "--user",
        "-u",
        help="Email of user to assign jobs to (default: first superuser or first user)",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be created without making changes",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "output",
        help="Output directory to scan (default: data/output)",
    )
    parser.add_argument(
        "--input-dir",
        "-i",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "input",
        help="Input directory for video files (default: data/input)",
    )

    args = parser.parse_args()

    # Get or create user
    if args.user:
        user = User.objects.filter(email=args.user).first()
        if not user:
            print(f"Error: User with email '{args.user}' not found")
            sys.exit(1)
    else:
        # Try to find a user
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            user = User.objects.first()
        if not user:
            print("Error: No users found. Create a user first or specify --user")
            sys.exit(1)

    print(f"Using user: {user.email}")
    print(f"Output directory: {args.output_dir}")
    print(f"Input directory: {args.input_dir}")

    if args.dry_run:
        print("\n*** DRY RUN MODE - No changes will be made ***")

    # Scan directories
    print("\nScanning output directory...")
    file_groups = scan_output_directory(args.output_dir)

    print(f"Found {len(file_groups)} lecture groups")

    print("\nScanning input directory for videos...")
    videos = scan_input_directory(args.input_dir)
    print(f"Found {len(videos)} video files")

    # Create jobs and artifacts
    jobs_created = 0
    artifacts_created = 0

    for label, files in sorted(file_groups.items()):
        # Try to match with a video file
        video_path = None
        for video_name, video_file in videos.items():
            if label.lower() in video_name.lower() or video_name.lower() in label.lower():
                video_path = video_file
                break

        job = create_job_and_artifacts(
            user=user,
            label=label,
            files=files,
            video_path=video_path,
            dry_run=args.dry_run,
        )

        if job and not args.dry_run:
            jobs_created += 1
            artifacts_created += len(files)

    print("\n" + "=" * 50)
    if args.dry_run:
        print(f"Would create {len(file_groups)} jobs")
    else:
        print(f"Created {jobs_created} jobs with {artifacts_created} artifacts")


if __name__ == "__main__":
    main()
