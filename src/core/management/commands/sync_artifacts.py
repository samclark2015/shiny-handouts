"""
Management command to sync artifacts from existing files on disk.

Creates or updates Artifact database entries for files in the output directory.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import Artifact, ArtifactType, Job


class Command(BaseCommand):
    help = "Sync artifacts from existing files on disk to the database"

    def add_arguments(self, parser):
        # Default output dir is relative to BASE_DIR's parent (project root)
        default_output = Path(settings.BASE_DIR).parent / "data" / "output"
        parser.add_argument(
            "--output-dir",
            type=str,
            default=str(default_output),
            help=f"Directory containing output files (default: {default_output})",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--job-id",
            type=int,
            help="Only sync artifacts for a specific job ID",
        )

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"])
        dry_run = options["dry_run"]
        job_id = options.get("job_id")

        if not output_dir.exists():
            raise CommandError(f"Output directory does not exist: {output_dir}")

        # Define file extension to artifact type mapping
        extension_map = {
            ".pdf": self._get_pdf_type,
            ".xlsx": lambda _: ArtifactType.EXCEL_STUDY_TABLE,
            ".mmd": lambda _: ArtifactType.MERMAID_MINDMAP,
        }

        # Get all jobs
        jobs = Job.objects.filter(status="completed")
        if job_id:
            jobs = jobs.filter(id=job_id)

        created_count = 0
        updated_count = 0
        skipped_count = 0

        # Scan output directory for files
        for file_path in output_dir.iterdir():
            self.stdout.write(f"Processing file: {file_path.name}")

            if not file_path.is_file():
                continue

            ext = file_path.suffix.lower()
            if ext not in extension_map:
                continue

            # Determine artifact type
            artifact_type = extension_map[ext](file_path.name)
            if artifact_type is None:
                self.stdout.write(
                    self.style.WARNING(f"  Skipping unknown PDF type: {file_path.name}")
                )
                skipped_count += 1
                continue

            # Try to match file to a job by filename prefix
            job = self._find_matching_job(file_path.name, jobs)

            if not job:
                self.stdout.write(self.style.WARNING(f"  No matching job for: {file_path.name}"))
                skipped_count += 1
                continue

            file_path_str = str(file_path.resolve())

            if dry_run:
                # Check if artifact exists
                existing = Artifact.objects.filter(job=job, file_path=file_path_str).first()
                if existing:
                    self.stdout.write(
                        f"  Would update: {file_path.name} -> Job: {job.title or job.label}"
                    )
                else:
                    self.stdout.write(
                        f"  Would create: {file_path.name} -> Job: {job.title or job.label}"
                    )
            else:
                # Create or update artifact
                artifact, created = Artifact.objects.update_or_create(
                    job=job,
                    file_path=file_path_str,
                    defaults={
                        "artifact_type": artifact_type,
                        "file_name": file_path.name,
                        "file_size": file_path.stat().st_size,
                    },
                )

                if created:
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  Created: {file_path.name} ({artifact.get_artifact_type_display()}) "
                            f"-> Job: {job.title or job.label}"
                        )
                    )
                else:
                    updated_count += 1
                    self.stdout.write(
                        f"  Updated: {file_path.name} ({artifact.get_artifact_type_display()}) "
                        f"-> Job: {job.title or job.label}"
                    )

        # Summary
        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes made"))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Sync complete: {created_count} created, {updated_count} updated, "
                    f"{skipped_count} skipped"
                )
            )

    def _get_pdf_type(self, filename: str) -> ArtifactType | None:
        """Determine PDF artifact type from filename."""
        lower = filename.lower()
        if "vignette" in lower:
            return ArtifactType.PDF_VIGNETTE
        elif lower.endswith(".pdf"):
            # Assume regular handout PDF
            return ArtifactType.PDF_HANDOUT
        return None

    def _find_matching_job(self, filename: str, jobs) -> Job | None:
        """Find a job that matches the given filename.

        Matches based on job title being a prefix of the filename.
        """
        # Strip extension and common suffixes
        name = filename
        for suffix in [".pdf", ".xlsx", ".mmd", " - Vignette Questions"]:
            if name.endswith(suffix):
                name = name[: -len(suffix)]

        # Also strip mindmap title suffixes (anything after " - ")
        base_name = name.rsplit(" - ", 1)[0] if " - " in name else name

        # Try to find exact title match first
        for job in jobs:
            title = job.title or job.label
            if title in (name, base_name):
                return job

        # Try prefix matching
        for job in jobs:
            title = job.title or job.label
            if name.startswith(title) or base_name.startswith(title):
                return job

        return None
