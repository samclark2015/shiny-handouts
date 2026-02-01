# Handout Generator - Project Instructions for AI Agents

> This document provides context and guidelines for LLM agents working with this codebase.

## Project Overview

**Handout Generator** is a Django web application that processes lecture video recordings to generate educational materials:
- **PDF Handouts** - 16-up slide layouts with transcribed captions
- **Excel Study Tables** - AI-generated study guides with key concepts
- **Vignette Questions** - AI-generated quiz questions
- **Mermaid Mindmaps** - Visual concept diagrams rendered as images

## Technology Stack

### Backend
| Component | Technology | Notes |
|-----------|------------|-------|
| Framework | **Django 5.2** | Not Flask (README may be outdated) |
| Task Queue | **Taskiq** with Redis broker | Not Celery - uses `taskiq-pipelines` for DAG workflows |
| Database | PostgreSQL (prod) / SQLite (dev) | Via `dj-database-url` |
| Caching | Redis | For AI response caching and task broker |
| Authentication | **django-allauth** with OpenID Connect | Authentik OAuth integration |
| AI/LLM | **OpenAI API** via `openai` package | Models: `gpt-4.1-nano` (fast), `gpt-5-mini` (smart) |

### Frontend
| Component | Technology | Notes |
|-----------|------------|-------|
| Templating | Django Templates | Located in `src/templates/` |
| Interactivity | **Alpine.js** | Lightweight reactivity - preferred over vanilla JS |
| Server Communication | **HTMX** | For partial page updates and SSE |
| Styling | **Tailwind CSS** (CDN) | With custom CSS in `src/static/css/` |
| Icons | Font Awesome 6 | CDN-loaded |

## Project Structure

```
shiny-handouts/
├── src/                          # Django project root
│   ├── manage.py                 # Django CLI entry point
│   ├── handout_generator/        # Django project settings
│   │   ├── settings.py           # Main configuration
│   │   ├── urls.py               # Root URL configuration
│   │   └── wsgi.py / asgi.py     # Server interfaces
│   ├── accounts/                 # User management app
│   │   ├── models.py             # User, SettingProfile models
│   │   ├── views.py              # Auth and settings views
│   │   └── adapter.py            # OAuth adapter
│   ├── core/                     # Main application logic
│   │   ├── models.py             # Job, Artifact models
│   │   ├── views/                # View modules (split by feature)
│   │   ├── urls/                 # URL modules (split by feature)
│   │   └── tasks/                # Taskiq pipeline system
│   │       ├── pipeline.py       # Pipeline creation/execution
│   │       ├── config.py         # Broker configuration
│   │       ├── stages/           # Individual pipeline stages
│   │       └── progress.py       # Progress reporting
│   ├── pipeline/                 # AI and processing utilities
│   │   ├── ai.py                 # OpenAI integration
│   │   ├── helpers.py            # Utility functions
│   │   └── schemas.py            # Pydantic models for AI responses
│   ├── prompts/                  # LLM prompt templates (Markdown)
│   ├── templates/                # Django HTML templates
│   └── static/                   # CSS, JS static files
├── data/                         # Runtime data (gitignored)
│   ├── db.sqlite3                # Development database
│   ├── cache/                    # AI response cache
│   ├── frames/                   # Extracted video frames
│   ├── input/                    # Uploaded files
│   └── output/                   # Generated artifacts
├── docker-compose.yml            # Production deployment
└── requirements.txt              # Python dependencies
```

## Key Patterns & Conventions

### 1. Taskiq Pipeline Architecture

The processing pipeline uses **Taskiq Pipelines** for chained async tasks:

```python
# src/core/tasks/pipeline.py
Pipeline(broker, generate_context_task)
    .call_next(download_video_task)
    .call_next(extract_captions_task)
    .call_next(match_frames_task)
    .call_next(transform_slides_ai_task)
    .call_next(generate_output_task)
    .call_next(compress_pdf_task)
    .call_next(generate_artifacts_task)  # Parallel: Excel, Vignette, Mindmap
    .call_next(finalize_job_task)
```

**Important**: Each stage receives a `PipelineContext` dataclass and returns it for the next stage.

### 2. AI Caching Pattern

AI calls are expensive. Use the `@ai_checkpoint` decorator to cache results:

```python
from core.cache import get_ai_cached_result, set_ai_cached_result

@ai_checkpoint
async def generate_captions(video_path: str) -> list[Caption]:
    # Results are cached based on function name + args
    ...
```

### 3. Frontend Interactivity with Alpine.js

**DO**: Use Alpine.js for all frontend interactivity
**DON'T**: Write verbose vanilla JavaScript event handlers

```html
<!-- Preferred Alpine.js pattern -->
<div x-data="{ open: false }">
    <button @click="open = !open">Toggle</button>
    <div x-show="open" x-transition>Content</div>
</div>

<!-- With HTMX for server communication -->
<button hx-post="/api/action" hx-target="#result">Submit</button>
```

### 4. Template Organization

- **Base template**: `src/templates/base.html` - includes Tailwind, Alpine, HTMX, Font Awesome
- **Partials**: `src/templates/partials/` - reusable components
- **Always include CSRF**: `hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'` on body tag

### 5. Styling Conventions

- **Put styles in CSS files**, not inline `<style>` tags
- Main styles: `src/static/css/styles.css`
- Use Tailwind utility classes for layout/spacing
- Use custom CSS for component-specific styles (mindmap controls, etc.)

### 6. Model Relationships

```
User (accounts.User)
 ├── SettingProfile (accounts.SettingProfile) - Multiple per user
 └── Job (core.Job) - Processing jobs
      ├── setting_profile → SettingProfile (optional)
      └── Artifact (core.Artifact) - Generated files
```

### 7. Setting Profiles

Users have configurable "Setting Profiles" for different lecture types:
- Customizable spreadsheet columns (JSON array)
- Custom prompts for Excel, Vignette, Mindmap generation
- One profile can be set as default

## Common Tasks & How-Tos

### Adding a New Pipeline Stage

1. Create stage file in `src/core/tasks/stages/`
2. Define async task function with `@broker.task` decorator
3. Import and add to pipeline in `src/core/tasks/pipeline.py`
4. Update `stages/__init__.py` exports

### Adding a New Artifact Type

1. Add choice to `ArtifactType` enum in `src/core/models.py`
2. Add generation logic in `src/core/tasks/stages/artifacts.py`
3. Add enable flag to `Job` model if user-configurable
4. Update UI in settings and job creation forms

### Modifying AI Prompts

Prompts are stored as Markdown files in `src/prompts/`:
- `generate_spreadsheet.md` - Excel study table
- `generate_vignette_questions.md` - Quiz questions
- `generate_mindmap.md` - Mermaid diagram
- `clean_transcript.md` - Transcript cleanup

Load with: `from pipeline.helpers import read_prompt`

### Working with HTMX + SSE

Job progress uses Server-Sent Events:
```html
<div hx-ext="sse" sse-connect="/job/{{ job.id }}/progress-stream/">
    <div sse-swap="progress">Loading...</div>
</div>
```

## Development Workflow

### Running Locally

```bash
# Terminal 1: Django dev server
cd src && python manage.py runserver

# Terminal 2: Taskiq worker
taskiq worker core.tasks:broker --workers 2

# Redis must be running (Docker or local)
docker run -d -p 6379:6379 redis:7-alpine
```

### Running with Docker Compose

```bash
docker compose up  # Starts web, taskiq-worker, db, redis
```

### Database Migrations

```bash
python src/manage.py makemigrations
python src/manage.py migrate
```

## Common Pitfalls to Avoid

1. **Don't use Celery patterns** - This project uses Taskiq, not Celery
2. **Don't inline JavaScript** - Use Alpine.js with `x-data` components
3. **Don't put styles in templates** - Add to CSS files
4. **Don't forget CSRF tokens** - Required for all POST requests
5. **Don't create duplicate imports** - Check existing imports in `__init__.py` files
6. **Drag-and-drop**: Use mouse events, not HTML5 Drag-and-Drop API (browser inconsistencies)

## File Naming Conventions

- **Views**: `src/core/views/<feature>.py`
- **URLs**: `src/core/urls/<feature>.py`
- **Pipeline stages**: `src/core/tasks/stages/<stage_name>.py`
- **Templates**: `src/templates/<feature>.html` or `src/templates/partials/<component>.html`
- **Static JS**: `src/static/js/<feature>.js`

## Testing

Test scripts in `scripts/`:
- `test_match_frames.py` - Frame extraction testing
- `test_vignette_pdf.py` - PDF generation testing

## Environment Variables

Key variables (see `.env.example`):
- `SECRET_KEY` - Django secret key
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis broker URL
- `OPENAI_API_KEY` - Required for AI features
- `DEBUG` - Enable debug mode (default: true)
