# Independent Code Review Report: Shiny-Handouts Project

**Date:** February 2, 2026
**Reviewer:** AI Code Reviewer
**Project:** Handout Generator (Shiny-Handouts)

---

## Executive Summary

This report provides an independent review of the Shiny-Handouts project, which automatically generates lecture handouts from video recordings using AI. The project demonstrates a sophisticated architecture leveraging Django, Celery, and OpenAI, but has several opportunities for improvement in error handling, async patterns, security, and UI/UX.

**Critical Findings:** 10 major areas identified
**Priority:** Focus on error handling, async consistency, and pipeline robustness first

---

## 1. Error Handling & Resilience

### Identified Issues
- **Resource leaks**: File handles left open without context managers (main.py:85-86)
- **Broad exception catching**: Without proper logging (storage.py:432 - catches all exceptions in `file_exists`)
- **No retry logic**: For AI API calls despite potential rate limiting/timeouts
- **No circuit breaker pattern**: For external dependencies (OpenAI, S3, Panopto)
- **Celery tasks lack graceful degradation**: When individual stages fail

### Improvement Strategies

#### 1. Implement tenacity library for retries
Add exponential backoff retry logic to all external API calls (OpenAI, S3, Panopto):

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
async def call_openai_api(...):
    # API call logic
```

Configure max retries (3-5) with exponential backoff (2^n seconds).

#### 2. Add structured error handling
- Create custom exception hierarchy:
  - `StorageError` - for S3/filesystem issues
  - `AIError` - for OpenAI/LLM failures
  - `PipelineError` - for task orchestration issues
- Replace bare `except Exception` with specific exceptions
- Add context to all logs: user_id, job_id, stage, timestamp

---

## 2. Async/Await Pattern Inconsistencies

### Identified Issues
- **Mixed sync/async code**: Creates event loop conflicts (storage.py:946-967 has `sync_*` wrappers using `run_until_complete`)
- **Event loop management**: Creating new event loops in sync context is fragile and can cause race conditions
- **Django ORM**: Queries mixed with async code without proper handling

### Improvement Strategies

#### 1. Migrate to Django 4.2+ async ORM fully
- Replace all `async_to_sync` decorators with native async views
- Use `asave()`, `aget()`, `acreate()` consistently instead of mixing sync and async patterns
- Example refactor:

```python
# Before
@async_to_sync
async def serve_file(request, job_id: int, artifact_id: int):
    artifact = await Artifact.objects.filter(...).afirst()

# After (native async view)
async def serve_file(request, job_id: int, artifact_id: int):
    artifact = await Artifact.objects.filter(...).afirst()
```

#### 2. Standardize on async patterns
- Remove all `sync_*` wrapper functions (storage.py:939-967)
- Either make callers async OR use a proper sync-to-async bridge with dedicated thread pool
- Consider using `asgiref.sync.async_to_sync` consistently instead of manual event loop management

---

## 3. Configuration & Settings Management

### Identified Issues
- **Manual DATABASE_URL parsing**: (settings.py:86-114) despite having `dj-database-url` installed
- **Environment variables**: Accessed directly without validation
- **No configuration schema**: Validation missing

### Improvement Strategies

#### 1. Use django-environ or pydantic-settings
Replace manual environment parsing:

```python
# Before: 30+ lines of manual parsing
if DATABASE_URL.startswith("postgresql://"):
    url = urllib.parse.urlparse(DATABASE_URL)
    DATABASES = {...}

# After: Using dj-database-url
import dj_database_url
DATABASES = {
    'default': dj_database_url.config(
        default='sqlite:///db.sqlite3',
        conn_max_age=600
    )
}
```

#### 2. Add configuration validation at startup
Create a Pydantic model for all settings:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openai_api_key: str
    s3_bucket_name: str
    redis_url: str

    class Config:
        env_file = '.env'

settings = Settings()  # Fails fast with clear errors
```

---

## 4. AI Caching & Cost Optimization

### Identified Issues
- **Custom caching decorator**: (ai.py:82-141) reinvents functionality Redis already provides
- **Cache keys not versioned**: Breaking changes in prompts invalidate cache silently
- **No cache eviction policy**: Or size limits defined
- **Pickle serialization**: For cache values (security risk)

### Improvement Strategies

#### 1. Replace with Redis-based semantic caching
```python
import hashlib
from django.core.cache import cache

def get_cache_key(func_name, prompt_file, *args, **kwargs):
    # Include prompt hash in cache key
    prompt_hash = hashlib.sha256(
        read_prompt(prompt_file).encode()
    ).hexdigest()[:8]

    arg_hash = hashlib.sha256(
        json.dumps(args + tuple(kwargs.items())).encode()
    ).hexdigest()[:8]

    return f"ai:{func_name}:v1:{prompt_hash}:{arg_hash}"

# Cache with TTL based on cost
cache.set(key, result, timeout=3600 * 24)  # 24h for expensive calls
```

#### 2. Add prompt versioning system
- Hash prompt files and include in cache keys
- When prompts change, new cache namespace created automatically
- Add CLI command: `python manage.py invalidate_ai_cache`

---

## 5. Storage Layer Optimization

### Identified Issues
- **S3 client created per-operation**: (storage.py:323-345) - no connection pooling
- **Mixed legacy and new path helpers**: (storage.py:605-660 are deprecated but still present)
- **No retry logic**: For S3 operations
- **File operations block async code paths**

### Improvement Strategies

#### 1. Implement connection pooling
```python
class S3Storage(Storage):
    _session = None

    @classmethod
    def get_session(cls):
        if cls._session is None:
            cls._session = aioboto3.Session()
        return cls._session

    @asynccontextmanager
    async def _get_client(self):
        session = self.get_session()
        async with session.client(
            's3',
            config=BotoConfig(
                max_pool_connections=50,
                connect_timeout=5,
                read_timeout=60
            )
        ) as client:
            yield client
```

#### 2. Clean up deprecated code paths
- Remove all legacy `get_s3_key()` and `get_local_path()` functions
- Migrate all callers to use `get_source_path()` and `get_job_path()`
- This removes ~100 lines of deprecated code and reduces maintenance burden

---

## 6. UI/UX Enhancements

### Identified Issues
- **No loading states**: For file downloads
- **File browser lacks search/filter**: (index.html:220-226)
- **No file size display**: In UI
- **No batch operations**: (delete multiple jobs/files)
- **Completed jobs query unbounded**: (models.py:27 - could return thousands)

### Improvement Strategies

#### 1. Add progressive enhancement
```javascript
// Loading spinner for downloads
htmx.on('htmx:beforeRequest', (event) => {
    if (event.detail.target.matches('.download-link')) {
        event.detail.target.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Downloading...';
    }
});

// Show download progress
htmx.on('htmx:xhr:progress', (event) => {
    if (event.lengthComputable) {
        const percent = (event.loaded / event.total) * 100;
        updateProgressBar(percent);
    }
});
```

#### 2. Implement search/filter/pagination
```html
<!-- Add to file browser -->
<div x-data="{ search: '' }" class="mb-4">
    <input
        type="text"
        x-model="search"
        placeholder="Search files..."
        class="w-full px-3 py-2 border rounded"
    >
</div>

<!-- Filter files client-side -->
<div x-show="file.name.toLowerCase().includes(search.toLowerCase())">
    <!-- File item -->
</div>
```

- Add date range filter for completed jobs
- Paginate completed jobs (20 per page) with infinite scroll
- Add bulk delete with confirmation modal

---

## 7. Security Hardening

### Identified Issues
- **Panopto authentication cookie**: Passed via URL query parameters (visible in logs, browser history)
- **No rate limiting**: On API endpoints
- **File upload validation**: Only checks extensions (index.html:88)
- **S3 presigned URLs**: Hardcoded to 1 hour expiration

### Improvement Strategies

#### 1. Implement secure token exchange
Replace URL-based cookie passing:

```python
# Instead of: /index?url=...&cookie=...
# Use POST with encrypted payload

from cryptography.fernet import Fernet

@csrf_exempt
async def panopto_redirect(request):
    encrypted_data = request.POST.get('data')
    cipher = Fernet(settings.SECRET_KEY[:32].encode())
    data = json.loads(cipher.decrypt(encrypted_data))

    # Store in session, redirect to clean URL
    request.session['panopto_auth'] = data
    return redirect('/')
```

For Panopto integration, use OAuth flow instead of cookie hijacking.

#### 2. Add comprehensive input validation
```python
import magic

def validate_video_file(file):
    # Check actual file type, not extension
    mime = magic.from_buffer(file.read(2048), mime=True)
    file.seek(0)

    if mime not in ['video/mp4', 'video/quicktime', 'video/x-msvideo']:
        raise ValidationError(f"Invalid file type: {mime}")

    # Check file size per user tier
    max_size = get_user_max_upload_size(request.user)
    if file.size > max_size:
        raise ValidationError(f"File too large: {file.size} > {max_size}")
```

Implement rate limiting:
```python
from django_ratelimit.decorators import ratelimit

@ratelimit(key='user', rate='10/h', method='POST')
async def upload_file(request):
    # Upload logic
```

---

## 8. Database Query Optimization

### Identified Issues
- **N+1 query problem**: Potential in job list views
- **No pagination**: On completed jobs (main.py:27)
- **Missing database indexes**: On frequently queried fields
- **No query monitoring**: Or slow query logging

### Improvement Strategies

#### 1. Add select_related/prefetch_related
```python
# Before: N+1 queries
jobs = Job.objects.filter(user=request.user)
for job in jobs:
    print(job.artifacts.all())  # Separate query per job

# After: 2 queries total
jobs = Job.objects.filter(user=request.user).prefetch_related('artifacts')
for job in jobs:
    print(job.artifacts.all())  # No additional query
```

Use Django Debug Toolbar in development to identify N+1 issues.

#### 2. Implement pagination and indexing
```python
# Add to models.py
class Job(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=['user', 'status', '-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]

# Add to views
from django.core.paginator import Paginator

def index(request):
    jobs = Job.objects.filter(user=request.user)
    paginator = Paginator(jobs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
```

Add database query logging:
```python
LOGGING = {
    'loggers': {
        'django.db.backends': {
            'level': 'DEBUG',
            'handlers': ['console'],
        }
    }
}
```

---

## 9. Pipeline Robustness

### Identified Issues
- **Tightly coupled stages**: (pipeline.py:23-33)
- **No partial success handling**: All-or-nothing approach
- **Failed jobs don't preserve**: Intermediate artifacts
- **No stage-level timeout**: Configuration

### Improvement Strategies

#### 1. Implement stage-level checkpointing
```python
class Pipeline:
    async def execute_stage(self, stage, job_id, data):
        checkpoint_key = f"checkpoint:{job_id}:{stage.name}"

        # Check for existing checkpoint
        cached = await cache.get(checkpoint_key)
        if cached:
            logger.info(f"Resuming from checkpoint: {stage.name}")
            return cached

        # Execute stage
        result = await stage.execute(job_id, data)

        # Save checkpoint
        await cache.set(checkpoint_key, result, timeout=86400)

        # Also save to database
        await StageResult.objects.acreate(
            job_id=job_id,
            stage=stage.name,
            data=result,
        )

        return result
```

#### 2. Add configurable timeouts and fallbacks
```python
from taskiq import TaskiqMessage
from taskiq_cancellation import with_cancellation

STAGE_TIMEOUTS = {
    'generate_context': 60,
    'download_video': 300,
    'extract_captions': 300,
    'generate_output': 600,
}

@with_cancellation
@broker.task(timeout=STAGE_TIMEOUTS['extract_captions'])
async def extract_captions_task(job_id, data):
    try:
        return await extract_captions(job_id, data)
    except TimeoutError:
        logger.warning(f"Caption extraction timed out for job {job_id}")
        # Graceful degradation: use dummy captions
        return {"captions": [], "warning": "Timed out"}
```

Add dead letter queue for failed stages:
```python
@broker.task(
    retry_on_error=True,
    max_retries=3,
    retry_delay=60,
    on_failure=send_to_dlq
)
async def risky_stage(job_id, data):
    # Stage logic
```

---

## 10. Testing & Observability

### Identified Issues
- **No visible test coverage**
- **Minimal logging structure**
- **No distributed tracing**: For pipeline stages
- **AI cost tracking exists**: But no alerting on anomalies

### Improvement Strategies

#### 1. Add OpenTelemetry instrumentation
```python
from opentelemetry import trace
from opentelemetry.instrumentation.celery import CeleryInstrumentor

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("extract_captions")
async def extract_captions_task(job_id, data):
    span = trace.get_current_span()
    span.set_attribute("job.id", job_id)
    span.set_attribute("user.id", data['user_id'])

    # Task logic

    span.set_attribute("captions.count", len(captions))
```

Add correlation IDs to all logs:
```python
import structlog

logger = structlog.get_logger()
logger = logger.bind(job_id=job_id, user_id=user_id)
logger.info("Starting caption extraction", duration=duration_ms)
```

#### 2. Implement cost anomaly detection
```python
# Add to monitoring
from django.db.models import Sum, Avg
from datetime import timedelta

async def check_cost_anomalies():
    # Cost per job in last hour
    recent_cost = await AIRequest.objects.filter(
        created_at__gte=timezone.now() - timedelta(hours=1)
    ).values('job_id').annotate(
        total_cost=Sum('estimated_cost_usd')
    )

    for job in recent_cost:
        if job['total_cost'] > 5.00:  # $5 threshold
            await alert_admin(
                f"High AI cost detected: Job {job['job_id']} - ${job['total_cost']}"
            )

# Track cache hit rates
cache_hits = AIRequest.objects.filter(cached=True).count()
total_requests = AIRequest.objects.count()
hit_rate = cache_hits / total_requests

if hit_rate < 0.60:  # 60% threshold
    await alert_admin(f"Low cache hit rate: {hit_rate:.1%}")
```

Create Grafana dashboard showing:
- Cost per user over time
- Cache hit rates by function
- Pipeline stage durations
- Error rates by stage

---

## Priority Recommendations

### Immediate (Week 1-2)
1. **Fix resource leaks** - Add context managers to file operations (main.py:85-86)
2. **Add retry logic** - Implement tenacity for all external API calls
3. **Standardize async patterns** - Remove sync wrappers, use native async

### Short-term (Month 1)
4. **Security hardening** - Fix Panopto authentication, add rate limiting
5. **Error handling** - Create exception hierarchy, add structured logging
6. **Query optimization** - Add indexes, implement pagination

### Medium-term (Month 2-3)
7. **Pipeline robustness** - Implement checkpointing, configurable timeouts
8. **UI/UX improvements** - Add search/filter, loading states, batch operations
9. **Observability** - Add OpenTelemetry, cost anomaly detection

### Long-term (Quarter 2)
10. **Comprehensive testing** - Add unit tests, integration tests, E2E tests
11. **Configuration management** - Migrate to pydantic-settings
12. **AI optimization** - Implement Redis-based semantic caching with versioning

---

## Conclusion

The Shiny-Handouts project demonstrates solid architectural foundations with a well-structured pipeline for video processing and AI-powered content generation. The most critical improvements needed are:

1. **Error handling and resilience** - To prevent job failures and data loss
2. **Async pattern consistency** - To eliminate race conditions and improve performance
3. **Pipeline robustness** - To enable partial recovery and graceful degradation

Addressing these three areas will significantly improve system reliability and user experience. The recommended improvements can be implemented incrementally without major architectural changes, allowing the system to continue operating while being enhanced.

The project would benefit from adopting more standardized patterns and libraries (tenacity, django-environ, OpenTelemetry) rather than custom implementations, which will reduce maintenance burden and improve reliability.
