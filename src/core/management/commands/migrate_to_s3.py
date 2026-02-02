"""
Management command to migrate existing local files to S3 storage.

This command uploads all artifact files from the local filesystem to S3
using the new user-based directory structure:
    {user_id}/sources/{source_id}/video.mp4
    {user_id}/sources/{source_id}/frames/{uuid}.jpg
    {user_id}/jobs/{job_id}/handout.pdf
"""

import asyncio
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import Artifact, Job
from core.storage import S3Storage, get_job_key, get_source_key, get_storage_config


class Command(BaseCommand):
    help = "Migrate existing local files to S3 storage with user-based paths"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-upload files even if they appear to already be on S3",
        )
        parser.add_argument(
            "--artifacts-only",
            action="store_true",
            help="Only migrate artifact files (output directory)",
        )
        parser.add_argument(
            "--frames-only",
            action="store_true",
            help="Only migrate frame files",
        )
        parser.add_argument(
            "--input-only",
            action="store_true",
            help="Only migrate input video files",
        )
        parser.add_argument(
            "--job-id",
            type=int,
            help="Only migrate files for a specific job ID",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=10,
            help="Number of files to upload concurrently (default: 10)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force = options["force"]
        artifacts_only = options["artifacts_only"]
        frames_only = options["frames_only"]
        input_only = options["input_only"]
        job_id = options.get("job_id")
        batch_size = options["batch_size"]

        # Verify S3 is configured
        config = get_storage_config()
        if not config.use_s3:
            raise CommandError(
                "S3 storage is not enabled. Set USE_S3_STORAGE=true in your environment."
            )

        if not config.bucket_name:
            raise CommandError("S3_BUCKET_NAME is not configured.")

        self.stdout.write(self.style.SUCCESS(f"Migrating files to S3 bucket: {config.bucket_name}"))
        self.stdout.write(
            self.style.SUCCESS("Using user-based path structure: {user_id}/sources|jobs/...")
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))

        # Determine what to migrate
        migrate_all = not (artifacts_only or frames_only or input_only)

        total_uploaded = 0
        total_skipped = 0
        total_errors = 0

        # Migrate artifacts (output directory)
        if migrate_all or artifacts_only:
            uploaded, skipped, errors = self._migrate_artifacts(dry_run, force, job_id, batch_size)
            total_uploaded += uploaded
            total_skipped += skipped
            total_errors += errors

        # Migrate frames
        if migrate_all or frames_only:
            uploaded, skipped, errors = self._migrate_frames(dry_run, force, job_id, batch_size)
            total_uploaded += uploaded
            total_skipped += skipped
            total_errors += errors

        # Migrate input videos
        if migrate_all or input_only:
            uploaded, skipped, errors = self._migrate_input_files(
                dry_run, force, job_id, batch_size
            )
            total_uploaded += uploaded
            total_skipped += skipped
            total_errors += errors

        # Summary
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(self.style.SUCCESS("Migration Summary"))
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(f"  Uploaded: {total_uploaded}")
        self.stdout.write(f"  Skipped:  {total_skipped}")
        if total_errors > 0:
            self.stdout.write(self.style.ERROR(f"  Errors:   {total_errors}"))
        else:
            self.stdout.write(f"  Errors:   {total_errors}")

        if dry_run:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING("This was a dry run. Run without --dry-run to apply changes.")
            )

    def _is_already_user_based_path(self, path: str) -> bool:
        """Check if a path already uses the user-based structure."""
        # User-based paths look like: {user_id}/sources/{source_id}/... or {user_id}/jobs/{job_id}/...
        parts = path.split("/")
        if len(parts) >= 3:
            # Check if first part is numeric (user_id) and second is 'sources' or 'jobs'
            try:
                int(parts[0])
                return parts[1] in ("sources", "jobs")
            except ValueError:
                return False
        return False

    def _migrate_artifacts(
        self, dry_run: bool, force: bool, job_id: int | None, batch_size: int
    ) -> tuple[int, int, int]:
        """Migrate artifact files from output directory to S3 with user-based paths."""
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("Migrating artifacts..."))

        output_dir = Path(settings.OUTPUT_DIR)
        if not output_dir.exists():
            self.stdout.write(f"  Output directory does not exist: {output_dir}")
            return 0, 0, 0

        # Get artifacts from database with job and user info
        artifacts = Artifact.objects.select_related("job", "job__user")
        if job_id:
            artifacts = artifacts.filter(job_id=job_id)

        uploaded = 0
        skipped = 0
        errors = 0

        for artifact in artifacts:
            job = artifact.job
            user_id = job.user_id

            # Check if already on S3 with user-based path
            if not force and self._is_already_user_based_path(artifact.file_path):
                self.stdout.write(f"  Skipping (already migrated): {artifact.file_name}")
                skipped += 1
                continue

            # Find local file - check multiple locations
            local_path = None

            # Try output directory with filename
            if (output_dir / artifact.file_name).exists():
                local_path = output_dir / artifact.file_name
            # Try the stored file_path
            elif os.path.exists(artifact.file_path):
                local_path = Path(artifact.file_path)
            # Try old S3-style paths (output/filename)
            elif artifact.file_path.startswith("output/"):
                old_local = output_dir / artifact.file_path[7:]  # strip 'output/'
                if old_local.exists():
                    local_path = old_local

            if not local_path or not local_path.exists():
                self.stdout.write(self.style.WARNING(f"  File not found: {artifact.file_name}"))
                skipped += 1
                continue

            # Generate new user-based S3 key
            new_s3_key = get_job_key(user_id, job.id, artifact.file_name)

            if dry_run:
                self.stdout.write(f"  Would upload: {local_path} -> {new_s3_key}")
                uploaded += 1
            else:
                try:
                    # Upload to S3 with user-based path
                    asyncio.get_event_loop().run_until_complete(
                        self._upload_file(str(local_path), new_s3_key)
                    )

                    # Update database record
                    artifact.file_path = new_s3_key
                    artifact.save(update_fields=["file_path"])

                    self.stdout.write(
                        self.style.SUCCESS(f"  Uploaded: {artifact.file_name} -> {new_s3_key}")
                    )
                    uploaded += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"  Error uploading {artifact.file_name}: {e}")
                    )
                    errors += 1

        return uploaded, skipped, errors

    def _migrate_frames(
        self, dry_run: bool, force: bool, job_id: int | None, batch_size: int
    ) -> tuple[int, int, int]:
        """Migrate frame files to S3 with user-based paths."""
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("Migrating frames..."))

        frames_dir = Path(settings.FRAMES_DIR)
        if not frames_dir.exists():
            self.stdout.write(f"  Frames directory does not exist: {frames_dir}")
            return 0, 0, 0

        uploaded = 0
        skipped = 0
        errors = 0

        # Get jobs with source_ids
        jobs = Job.objects.filter(source_id__isnull=False).select_related("user")
        if job_id:
            jobs = jobs.filter(id=job_id)

        # Build mapping of source_id -> user_id (use first job's user for shared sources)
        source_to_user = {}
        for job in jobs:
            if job.source_id and job.source_id not in source_to_user:
                source_to_user[job.source_id] = job.user_id

        # Also scan directory for any source_id folders not in DB
        for source_dir in frames_dir.iterdir():
            if source_dir.is_dir() and source_dir.name not in source_to_user:
                # No user mapping - skip orphaned frames
                self.stdout.write(
                    self.style.WARNING(f"  Skipping orphaned source (no job): {source_dir.name}")
                )

        for source_id, user_id in source_to_user.items():
            source_dir = frames_dir / source_id
            if not source_dir.exists():
                continue

            self.stdout.write(f"  Processing source: {source_id} (user: {user_id})")

            for frame_file in source_dir.iterdir():
                if not frame_file.is_file():
                    continue

                # Only process image files
                if frame_file.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                    continue

                # Generate user-based S3 key with frames/ subdirectory
                new_s3_key = get_source_key(user_id, source_id, f"frames/{frame_file.name}")

                if dry_run:
                    self.stdout.write(f"    Would upload: {frame_file.name} -> {new_s3_key}")
                    uploaded += 1
                else:
                    try:
                        asyncio.get_event_loop().run_until_complete(
                            self._upload_file(str(frame_file), new_s3_key)
                        )
                        self.stdout.write(f"    Uploaded: {frame_file.name}")
                        uploaded += 1
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"    Error: {frame_file.name}: {e}"))
                        errors += 1

        return uploaded, skipped, errors

    def _migrate_input_files(
        self, dry_run: bool, force: bool, job_id: int | None, batch_size: int
    ) -> tuple[int, int, int]:
        """Migrate input video files to S3 with user-based paths."""
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("Migrating input files..."))

        input_dir = Path(settings.INPUT_DIR)
        if not input_dir.exists():
            self.stdout.write(f"  Input directory does not exist: {input_dir}")
            return 0, 0, 0

        uploaded = 0
        skipped = 0
        errors = 0

        # Get jobs that have video_path pointing to local files
        jobs = Job.objects.filter(video_path__isnull=False).select_related("user")
        if job_id:
            jobs = jobs.filter(id=job_id)

        # Build mapping of video filename -> (job, user_id, source_id)
        video_to_job = {}
        for job in jobs:
            if job.video_path:
                # Extract filename from path
                video_filename = os.path.basename(job.video_path)
                video_to_job[video_filename] = (job, job.user_id, job.source_id)

        for input_file in input_dir.iterdir():
            if not input_file.is_file():
                continue

            # Only process video files
            if input_file.suffix.lower() not in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
                continue

            # Find job for this video
            if input_file.name not in video_to_job:
                self.stdout.write(
                    self.style.WARNING(f"  Skipping orphaned video (no job): {input_file.name}")
                )
                skipped += 1
                continue

            job, user_id, source_id = video_to_job[input_file.name]

            if not source_id:
                self.stdout.write(
                    self.style.WARNING(f"  Skipping (no source_id on job): {input_file.name}")
                )
                skipped += 1
                continue

            # Check if already migrated
            if not force and self._is_already_user_based_path(job.video_path or ""):
                self.stdout.write(f"  Skipping (already migrated): {input_file.name}")
                skipped += 1
                continue

            # Generate user-based S3 key
            new_s3_key = get_source_key(user_id, source_id, "video.mp4")

            if dry_run:
                self.stdout.write(f"  Would upload: {input_file.name} -> {new_s3_key}")
                uploaded += 1
            else:
                try:
                    asyncio.get_event_loop().run_until_complete(
                        self._upload_file(str(input_file), new_s3_key)
                    )

                    # Update job's video_path
                    job.video_path = new_s3_key
                    job.save(update_fields=["video_path"])

                    self.stdout.write(
                        self.style.SUCCESS(f"  Uploaded: {input_file.name} -> {new_s3_key}")
                    )
                    uploaded += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  Error: {input_file.name}: {e}"))
                    errors += 1

        return uploaded, skipped, errors

    async def _upload_file(self, local_path: str, s3_key: str) -> None:
        """Upload a file to S3 with the given key."""
        config = get_storage_config()
        storage = S3Storage(config)
        
        await storage.upload_file(local_path, s3_key)
