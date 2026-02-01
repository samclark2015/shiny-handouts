"""
Management command to migrate existing local files to S3 storage.

This command uploads all artifact files from the local filesystem to S3
and updates the database records with the new S3 keys.
"""

import asyncio
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import Artifact, Lecture
from core.storage import get_s3_key, get_storage_config, upload_file


class Command(BaseCommand):
    help = "Migrate existing local files to S3 storage"

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
            "--lecture-id",
            type=int,
            help="Only migrate files for a specific lecture ID",
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
        lecture_id = options.get("lecture_id")
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

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))

        # Determine what to migrate
        migrate_all = not (artifacts_only or frames_only or input_only)

        total_uploaded = 0
        total_skipped = 0
        total_errors = 0

        # Migrate artifacts (output directory)
        if migrate_all or artifacts_only:
            uploaded, skipped, errors = self._migrate_artifacts(
                dry_run, force, lecture_id, batch_size
            )
            total_uploaded += uploaded
            total_skipped += skipped
            total_errors += errors

        # Migrate frames
        if migrate_all or frames_only:
            uploaded, skipped, errors = self._migrate_frames(dry_run, force, lecture_id, batch_size)
            total_uploaded += uploaded
            total_skipped += skipped
            total_errors += errors

        # Migrate input videos
        if migrate_all or input_only:
            uploaded, skipped, errors = self._migrate_input_files(dry_run, force, batch_size)
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

    def _migrate_artifacts(
        self, dry_run: bool, force: bool, lecture_id: int | None, batch_size: int
    ) -> tuple[int, int, int]:
        """Migrate artifact files from output directory to S3."""
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("Migrating artifacts..."))

        output_dir = Path(settings.OUTPUT_DIR)
        if not output_dir.exists():
            self.stdout.write(f"  Output directory does not exist: {output_dir}")
            return 0, 0, 0

        # Get artifacts from database
        artifacts = Artifact.objects.select_related("lecture")
        if lecture_id:
            artifacts = artifacts.filter(lecture_id=lecture_id)

        uploaded = 0
        skipped = 0
        errors = 0

        for artifact in artifacts:
            # Check if already on S3 (path starts with output/)
            if not force and artifact.file_path.startswith("output/"):
                self.stdout.write(f"  Skipping (already on S3): {artifact.file_name}")
                skipped += 1
                continue

            # Find local file
            local_path = output_dir / artifact.file_name
            if not local_path.exists():
                # Try the stored file_path
                if os.path.exists(artifact.file_path):
                    local_path = Path(artifact.file_path)
                else:
                    self.stdout.write(self.style.WARNING(f"  File not found: {artifact.file_name}"))
                    skipped += 1
                    continue

            # Generate S3 key
            s3_key = get_s3_key("output", artifact.file_name)

            if dry_run:
                self.stdout.write(f"  Would upload: {local_path} -> {s3_key}")
                uploaded += 1
            else:
                try:
                    # Upload to S3
                    storage_path = asyncio.get_event_loop().run_until_complete(
                        upload_file(str(local_path), "output", artifact.file_name)
                    )

                    # Update database record
                    artifact.file_path = storage_path
                    artifact.save(update_fields=["file_path"])

                    self.stdout.write(self.style.SUCCESS(f"  Uploaded: {artifact.file_name}"))
                    uploaded += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"  Error uploading {artifact.file_name}: {e}")
                    )
                    errors += 1

        return uploaded, skipped, errors

    def _migrate_frames(
        self, dry_run: bool, force: bool, lecture_id: int | None, batch_size: int
    ) -> tuple[int, int, int]:
        """Migrate frame files to S3."""
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("Migrating frames..."))

        frames_dir = Path(settings.FRAMES_DIR)
        if not frames_dir.exists():
            self.stdout.write(f"  Frames directory does not exist: {frames_dir}")
            return 0, 0, 0

        uploaded = 0
        skipped = 0
        errors = 0

        # Get lectures to find source_ids
        lectures = Lecture.objects.all()
        if lecture_id:
            lectures = lectures.filter(id=lecture_id)

        source_ids = set(lectures.values_list("source_id", flat=True))

        # Also scan directory for any source_id folders
        for source_dir in frames_dir.iterdir():
            if source_dir.is_dir():
                source_ids.add(source_dir.name)

        for source_id in source_ids:
            if not source_id:
                continue

            source_dir = frames_dir / source_id
            if not source_dir.exists():
                continue

            self.stdout.write(f"  Processing source: {source_id}")

            for frame_file in source_dir.iterdir():
                if not frame_file.is_file():
                    continue

                # Only process image files
                if frame_file.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                    continue

                if dry_run:
                    self.stdout.write(f"    Would upload: {frame_file.name}")
                    uploaded += 1
                else:
                    try:
                        asyncio.get_event_loop().run_until_complete(
                            upload_file(
                                str(frame_file),
                                "frames",
                                frame_file.name,
                                source_id=source_id,
                            )
                        )
                        self.stdout.write(f"    Uploaded: {frame_file.name}")
                        uploaded += 1
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"    Error: {frame_file.name}: {e}"))
                        errors += 1

        return uploaded, skipped, errors

    def _migrate_input_files(
        self, dry_run: bool, force: bool, batch_size: int
    ) -> tuple[int, int, int]:
        """Migrate input video files to S3."""
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("Migrating input files..."))

        input_dir = Path(settings.INPUT_DIR)
        if not input_dir.exists():
            self.stdout.write(f"  Input directory does not exist: {input_dir}")
            return 0, 0, 0

        uploaded = 0
        skipped = 0
        errors = 0

        for input_file in input_dir.iterdir():
            if not input_file.is_file():
                continue

            # Only process video files
            if input_file.suffix.lower() not in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
                continue

            if dry_run:
                self.stdout.write(f"  Would upload: {input_file.name}")
                uploaded += 1
            else:
                try:
                    asyncio.get_event_loop().run_until_complete(
                        upload_file(str(input_file), "input", input_file.name)
                    )
                    self.stdout.write(self.style.SUCCESS(f"  Uploaded: {input_file.name}"))
                    uploaded += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  Error: {input_file.name}: {e}"))
                    errors += 1

        return uploaded, skipped, errors
