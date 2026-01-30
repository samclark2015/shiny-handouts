## Plan: Refactor Handout Generator to Production Architecture ✅ COMPLETED

Migrate from NiceGUI to Flask + HTMX, replace the bespoke async pipeline with Celery using Redis as both broker and cache, and add PostgreSQL/SQLite-backed state management. The 9-stage video processing pipeline will become Celery task chains with progress tracking, cancellation, and retry support.

### Steps

1. ✅ **Set up Flask + SQLAlchemy foundation** — Created database models for `User`, `Job`, `Lecture`, and `Artifact` in models.py, supporting hierarchical organization (Date → Lecture → Artifacts) with configurable DB backend via `DATABASE_URL` environment variable.

2. ✅ **Configure Celery with Redis** — Added celery_app.py using Redis as broker, result backend, and stage-level cache (replacing pipeline/cache.py); converted the 9 stages from pipeline/process.py into chained Celery tasks with `bind=True` for `self.update_state()` progress reporting.

3. ✅ **Build Flask + HTMX frontend** — Created pages/index.py as Jinja2 templates with HTMX attributes for: file upload with progress (`hx-post`), task cards that poll for updates (`hx-trigger="every 2s"`), cancel buttons (`hx-delete`), and a nested file browser (Date → Lecture → Artifacts).

4. ✅ **Implement SSE progress endpoint** — Added a `/jobs/<id>/progress` Server-Sent Events route that streams Celery task state updates; HTMX's `sse:` extension will consume these for real-time progress bars without full page reloads.

5. ✅ **Migrate OAuth to Flask-Dance** — Ported Authentik integration from auth.py to Authlib with Flask, preserving the existing OAuth flow and session handling.

6. ✅ **Add job durability and controls** — Stored job metadata in the database with status enum (`pending`, `running`, `completed`, `failed`, `cancelled`); implemented cancel via Celery `revoke(terminate=True)` and retry-on-demand by re-queuing from the database record.

### Further Considerations

1. **Redis caching granularity?** Cache at stage level (like current diskcache) using source hash keys, or cache at sub-operation level (e.g., individual AI calls) — recommend **stage-level** to match existing pattern and simplify migration.
**Answer**: Stage-level caching.

2. **Database migration tool?** Use Alembic for schema migrations or Flask-Migrate (Alembic wrapper) — recommend **Flask-Migrate** for tighter Flask integration.
**Answer**: Use Flask-Migrate
