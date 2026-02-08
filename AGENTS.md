# Handout Generator - Claude Code Agent Instructions

> This document provides context and guidelines for Claude Code when working with this codebase.

## Quick Start

This is **Handout Generator**, a Django web application that processes lecture videos to generate educational materials (PDFs, Excel study guides, quiz questions, and mindmaps).

**Key Technologies**: Django 5.2 | Taskiq (not Celery!) | PostgreSQL | Redis | Alpine.js + HTMX | Tailwind CSS

## Critical Context

### What This Project Does

The application processes lecture video recordings through an async pipeline to generate:
- **PDF Handouts** - 16-up slide layouts with captions
- **Excel Study Tables** - AI-generated study guides
- **Vignette Questions** - AI-generated quiz questions
- **Mermaid Mindmaps** - Visual concept diagrams

### Architecture Overview

```
Video Upload → Taskiq Pipeline → Multiple Artifacts
                    ↓
    [Extract Frames, Captions, AI Processing]
                    ↓
          Generate Output Files
```

**Pipeline System**: Uses `taskiq-pipelines` for DAG-based async workflows (see `src/core/tasks/pipeline.py:83-91`)

## Project Structure Guide

```
src/
├── handout_generator/     # Django settings and config
├── accounts/              # User auth (django-allauth + OAuth)
├── core/                  # Main app
│   ├── models.py          # Job, Artifact models
│   ├── views/             # Split by feature
│   ├── urls/              # Split by feature
│   └── tasks/             # Taskiq pipeline system
│       ├── pipeline.py    # Pipeline definition
│       ├── stages/        # Individual processing stages
│       └── progress.py    # SSE progress reporting
├── pipeline/              # AI and utilities
│   ├── ai.py              # OpenAI integration
│   ├── helpers.py         # Utility functions
│   └── schemas.py         # Pydantic models
├── prompts/               # LLM prompt templates (Markdown)
├── templates/             # Django HTML templates
└── static/                # CSS, JS files

data/                      # Runtime data (gitignored)
├── db.sqlite3             # Dev database
├── cache/                 # AI response cache
├── input/                 # Uploaded files
└── output/                # Generated artifacts
```

## When Exploring This Codebase

### Use the Task Tool with Explore Agent

For broad exploratory questions, always use the Task tool with `subagent_type=Explore`:

**Good examples**:
- "Where is error handling done?"
- "How does the AI caching work?"
- "Show me the authentication flow"

**Bad examples** (just read the file directly):
- "Read the Job model" → Use Read on `src/core/models.py`
- "Show me the main view" → Use Read on specific file

### Key Files to Know

| Purpose | File Location |
|---------|--------------|
| Pipeline definition | `src/core/tasks/pipeline.py:83-91` |
| Job/Artifact models | `src/core/models.py` |
| AI integration | `src/pipeline/ai.py` |
| Main settings | `src/handout_generator/settings.py` |
| Base template | `src/templates/base.html` |

## Technology-Specific Guidance

### 1. Task Queue: Taskiq (NOT Celery!)

**Critical**: This project uses **Taskiq**, not Celery. Don't suggest Celery patterns.

```python
# Taskiq task definition
from core.tasks.config import broker

@broker.task
async def process_stage(ctx: PipelineContext) -> PipelineContext:
    # Process and return context
    return ctx
```

**Pipeline pattern** (`src/core/tasks/pipeline.py:83-91`):
```python
Pipeline(broker, generate_context_task)
    .call_next(download_video_task)
    .call_next(extract_captions_task)
    # ... more stages
```

Each stage receives and returns a `PipelineContext` dataclass.

### 2. Frontend: Alpine.js + HTMX

**Always prefer Alpine.js** for interactivity, not vanilla JavaScript:

```html
<!-- Good: Alpine.js -->
<div x-data="{ open: false }">
    <button @click="open = !open">Toggle</button>
    <div x-show="open" x-transition>Content</div>
</div>

<!-- Bad: Verbose vanilla JS -->
<button onclick="document.getElementById('x').classList.toggle('hidden')">
```

**HTMX for server communication**:
```html
<button hx-post="/api/action"
        hx-target="#result"
        hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
    Submit
</button>
```

**Server-Sent Events for progress**:
```html
<div hx-ext="sse" sse-connect="/job/{{ job.id }}/progress-stream/">
    <div sse-swap="progress">Loading...</div>
</div>
```

### 3. Styling: Tailwind CSS + Custom CSS

**Important**: Put styles in CSS files (`src/static/css/`), **not** inline `<style>` tags in templates.

- Use Tailwind utilities for layout/spacing
- Use custom CSS for component-specific styles
- Main stylesheet: `src/static/css/styles.css`

### 4. AI Integration & Caching

AI calls are expensive. Results are cached using decorators:

```python
from core.cache import ai_checkpoint

@ai_checkpoint
async def generate_content(input_data: str) -> dict:
    # Results cached based on function name + args
    response = await call_openai_api(...)
    return response
```

**Models used**:
- `gpt-4.1-nano` - Fast, cheaper
- `gpt-5-mini` - Smarter, more expensive

**Prompts**: Stored as Markdown files in `src/prompts/`

## Common Patterns You'll Encounter

### 1. Model Relationships

```
User (accounts.User)
 ├── SettingProfile (accounts.SettingProfile) - Multiple per user
 └── Job (core.Job) - Processing jobs
      ├── setting_profile → SettingProfile (optional)
      └── Artifact (core.Artifact) - Generated files
```

### 2. Setting Profiles

Users can create multiple "Setting Profiles" for different lecture types:
- Custom spreadsheet columns (JSON array)
- Custom prompts for Excel, Vignette, Mindmap
- One can be set as default

### 3. CSRF Protection

**Always include CSRF tokens** for POST requests:
```html
<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
```

## When Making Changes

### Adding a New Pipeline Stage

1. Create file: `src/core/tasks/stages/<stage_name>.py`
2. Define async function with `@broker.task`
3. Accept and return `PipelineContext`
4. Import and add to pipeline in `src/core/tasks/pipeline.py:83-91`
5. Export in `src/core/tasks/stages/__init__.py`

### Adding a New Artifact Type

1. Add to `ArtifactType` enum in `src/core/models.py`
2. Add generation logic in `src/core/tasks/stages/artifacts.py`
3. Add enable flag to `Job` model if user-configurable
4. Update UI in templates

### Modifying AI Prompts

1. Edit Markdown files in `src/prompts/`:
   - `generate_spreadsheet.md`
   - `generate_vignette_questions.md`
   - `generate_mindmap.md`
   - `clean_transcript.md`

2. Load with: `from pipeline.helpers import read_prompt`

### Working with Templates

- **Base template**: `src/templates/base.html` (includes all CDNs)
- **Partials**: `src/templates/partials/`
- **Always extend base**: `{% extends "base.html" %}`

## Common Pitfalls - DO NOT

1. ❌ **Don't suggest Celery** - Use Taskiq patterns only
2. ❌ **Don't write vanilla JS event handlers** - Use Alpine.js
3. ❌ **Don't add inline styles in templates** - Use CSS files
4. ❌ **Don't forget CSRF tokens** - Required for all POST/mutations
5. ❌ **Don't use HTML5 Drag-and-Drop API** - Use mouse events (browser inconsistencies)
6. ❌ **Don't add unnecessary abstractions** - Keep it simple

## Development Context

### Running the Application

The user typically runs this with:

```bash
# Terminal 1: Django
python manage.py runserver

# Terminal 2: Taskiq worker
taskiq worker core.tasks:broker --workers 2

# Redis (via Docker or local)
docker run -d -p 6379:6379 redis:7-alpine
```

Or via Docker Compose:
```bash
docker compose up  # Starts web, worker, db, redis
```

### Database Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### Key Environment Variables

- `SECRET_KEY` - Django secret
- `DATABASE_URL` - PostgreSQL connection
- `REDIS_URL` - Redis broker
- `OPENAI_API_KEY` - Required for AI features
- `DEBUG` - Debug mode (default: true)

**S3 Storage** (optional): Set `USE_S3_STORAGE=true` for cloud storage

## Tool Usage Guidelines

### When to Use Each Tool

- **Read**: For specific files you know about
- **Glob**: To find files by pattern (`**/*.py`)
- **Grep**: To search for specific code/text
- **Task (Explore)**: For broad questions about code organization
- **Edit**: To modify existing files (preferred over Write)
- **Write**: Only for new files (use sparingly)

### Planning Complex Changes

For multi-file changes or new features:

1. **Use EnterPlanMode** to explore and design first
2. Create a **TodoWrite** list to track steps
3. Ask clarifying questions with **AskUserQuestion** if needed
4. Mark todos as `in_progress` before starting
5. Mark `completed` immediately after finishing each task

## Code Style Conventions

### File Naming

- Views: `src/core/views/<feature>.py`
- URLs: `src/core/urls/<feature>.py`
- Pipeline stages: `src/core/tasks/stages/<stage_name>.py`
- Templates: `src/templates/<feature>.html` or `src/templates/partials/<component>.html`

### Python Code

- Use **async/await** for Taskiq tasks
- Type hints encouraged (especially for AI schemas)
- Pydantic models for structured AI outputs (`src/pipeline/schemas.py`)

### Template Code

- Use Django template syntax
- Alpine.js for interactivity (`x-data`, `@click`, `x-show`)
- HTMX attributes for server communication
- Tailwind classes for styling

## Git Workflow

- **Current branch**: `celery` (though project doesn't use Celery!)
- **Main branch**: `main`
- Create meaningful commit messages
- Don't commit unless user explicitly asks

## Need More Context?

If you encounter something unclear:

1. **Check the copilot instructions**: `.github/copilot-instructions.md` has detailed technical information
2. **Explore with Task tool**: Use `subagent_type=Explore` for broad questions
3. **Read key files**: Models, pipeline, settings files
4. **Ask the user**: Use AskUserQuestion for clarifications

## Summary: Key Things to Remember

1. **Taskiq, not Celery** - Different task queue system
2. **Alpine.js for JS** - Avoid vanilla JavaScript event handlers
3. **Styles in CSS files** - Not inline in templates
4. **CSRF tokens required** - For all POST requests
5. **AI responses are cached** - Don't bypass the cache
6. **Use existing patterns** - Don't over-engineer or add unnecessary features

---

*This project follows the principle of simplicity: only add what's needed, prefer editing over creating new files, and trust existing patterns.*
