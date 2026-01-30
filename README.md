# Shiny Handouts

A web application for generating lecture handouts from video recordings. Automatically extracts slides, transcribes audio, and generates:
- 📄 **PDF Handouts** - 16-up slide layouts with transcribed captions
- 📊 **Excel Study Tables** - AI-generated study guides with key concepts
- 📝 **Vignette Questions** - AI-generated quiz questions for each learning objective

## Architecture

This application uses a modern production-ready stack:

- **Frontend**: Flask + HTMX with Tailwind CSS
- **Backend**: Flask with SQLAlchemy ORM
- **Task Queue**: Celery with Redis broker
- **Caching**: Redis for stage-level pipeline caching
- **Database**: PostgreSQL (production) or SQLite (development)
- **Authentication**: OAuth 2.0 with Authentik (via Flask-Dance/Authlib)

## Quick Start

### Development (Local)

1. **Clone and install dependencies:**
   ```bash
   git clone https://github.com/samclark2015/shiny-handouts.git
   cd shiny-handouts
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start Redis (required for Celery):**
   ```bash
   # Using Docker
   docker run -d -p 6379:6379 redis:7-alpine
   
   # Or install locally
   brew install redis && brew services start redis
   ```

4. **Initialize the database:**
   ```bash
   flask db init
   flask db migrate
   flask db upgrade
   ```

5. **Start the Flask application:**
   ```bash
   flask run --debug
   ```

6. **Start the Celery worker (in a separate terminal):**
   ```bash
   celery -A celery_app worker --loglevel=info
   ```

### Production (Docker Compose)

1. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with production values
   ```

2. **Start all services:**
   ```bash
   docker-compose up -d
   ```

3. **Initialize the database:**
   ```bash
   docker-compose exec web flask db upgrade
   ```

The application will be available at `http://localhost:5000`.

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask secret key for sessions | `dev-secret-key` |
| `DATABASE_URL` | Database connection URL | `sqlite:///data/shiny_handouts.db` |
| `REDIS_URL` | Redis URL for Celery broker | `redis://localhost:6379/0` |
| `REDIS_CACHE_URL` | Redis URL for caching | `redis://localhost:6379/1` |
| `OAUTH_URL` | Authentik OpenID Connect discovery URL | - |
| `OAUTH_CLIENT_ID` | OAuth client ID | - |
| `OAUTH_CLIENT_SECRET` | OAuth client secret | - |
| `OPENAI_API_KEY` | OpenAI API key for AI features | - |

### Database Support

- **SQLite**: Default for development (`sqlite:///data/shiny_handouts.db`)
- **PostgreSQL**: Recommended for production (`postgresql://user:pass@host:5432/db`)
- **MySQL/MariaDB**: Supported (`mysql+pymysql://user:pass@host:3306/db`)

## Pipeline Stages

The video processing pipeline consists of 9 stages:

1. **Generate Context** - Initialize processing context
2. **Download Video** - Download from URL, Panopto, or use uploaded file
3. **Extract Captions** - Transcribe audio using OpenAI Whisper
4. **Match Frames** - Match video frames to captions using structural similarity
5. **Transform with AI** - Clean transcripts using AI
6. **Generate PDF** - Create PDF handout with slides and captions
7. **Compress PDF** - Optimize PDF size with Ghostscript
8. **Generate Spreadsheet** - Create AI-powered study table
9. **Generate Vignette** - Create AI-powered quiz questions

Each stage is cached independently, allowing failed pipelines to resume from where they left off.

## Job Management

- **Progress Tracking**: Real-time progress updates via Server-Sent Events (SSE)
- **Cancellation**: Cancel running jobs at any time
- **Retry**: Retry failed or cancelled jobs from the database record
- **Durability**: Job state persisted to database, survives restarts

## API Endpoints

### Main Routes
- `GET /` - Dashboard with file upload and job list
- `GET /files/<filename>` - Serve generated files

### API Routes (HTMX)
- `POST /api/upload` - Upload and process video file
- `POST /api/url` - Process video from URL
- `POST /api/panopto` - Process Panopto video
- `GET /api/jobs` - List user's jobs
- `GET /api/jobs/<id>` - Get job status
- `DELETE /api/jobs/<id>/cancel` - Cancel a job
- `POST /api/jobs/<id>/retry` - Retry a failed job
- `GET /api/jobs/<id>/progress` - SSE progress stream
- `GET /api/files` - File browser

### Auth Routes
- `GET /auth/login` - Login page
- `GET /auth/login/start` - Start OAuth flow
- `GET /auth/callback` - OAuth callback
- `GET /auth/logout` - Logout

## Development

### Running Tests
```bash
pytest
```

### Database Migrations
```bash
flask db migrate -m "Description of changes"
flask db upgrade
```

### Code Structure

```
shiny-handouts/
├── app.py              # Flask application factory
├── models.py           # SQLAlchemy database models
├── routes.py           # Flask routes and API endpoints
├── tasks.py            # Celery tasks (pipeline stages)
├── celery_app.py       # Celery configuration
├── cache.py            # Redis caching layer
├── config.py           # Configuration management
├── oauth.py            # OAuth integration
├── pipeline/           # Original pipeline code (reference)
├── templates/flask/    # Jinja2 templates
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   └── partials/       # HTMX partial templates
└── docker-compose.yml  # Production deployment
```

## License

MIT License
