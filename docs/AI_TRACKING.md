# AI Request Tracking & Cost Analysis

This feature adds comprehensive tracking of all AI/LLM API requests with user/job tagging and cost estimation.

## Features

### 1. **Request Tracking**
Every AI API call is automatically logged with:
- Function name (e.g., `generate_captions`, `generate_spreadsheet_helper`)
- Model used (e.g., `gpt-4.1-nano`, `gpt-5-mini`, `whisper-1`)
- User and Job associations
- Token usage (prompt + completion)
- Estimated cost in USD
- Request duration in milliseconds
- Whether the result was cached
- Success/failure status with error messages

### 2. **User/Job Context Tagging**
The pipeline automatically sets the user and job context at the start of each processing job, so all subsequent AI requests are tagged with:
- `user_id` - Which user initiated the request
- `job_id` - Which job the request is associated with

### 3. **Cost Estimation**
Costs are calculated based on model pricing:
```python
MODEL_PRICING = {
    "gpt-4.1-nano": (0.10, 0.40),  # USD per 1M tokens (input, output)
    "gpt-5-mini": (0.30, 1.20),
    "whisper-1": (0.006, 0.006),   # Approximated
}
```

**Note**: These are example prices. Update them in `src/pipeline/ai.py` to match actual OpenAI pricing.

### 4. **Analytics Dashboard**
Users can view their AI usage at `/analytics/`:
- Total requests and tokens used
- Estimated costs
- Cache hit rate (% of requests served from cache)
- Breakdown by model
- Time period filters (7/30/90/365 days)

### 5. **Django Admin Interface**
Admins can view detailed AI request logs in the admin panel at `/admin/core/airequest/`:
- Filter by model, function, cached status, success
- Search by user email or job title
- View token usage and costs
- Read-only interface (requests are auto-generated)

## Database Schema

```python
class AIRequest(models.Model):
    # Request metadata
    function_name = CharField(max_length=100)
    model = CharField(max_length=50)
    
    # Relationships
    user = ForeignKey(User, null=True)
    job = ForeignKey(Job, null=True)
    
    # Token usage and costs
    prompt_tokens = IntegerField()
    completion_tokens = IntegerField()
    total_tokens = IntegerField()
    estimated_cost_usd = DecimalField(max_digits=10, decimal_places=6)
    
    # Performance
    duration_ms = IntegerField()
    
    # Status
    cached = BooleanField()
    success = BooleanField()
    error_message = TextField()
    
    # Timing
    created_at = DateTimeField()
```

## Analytics Utilities

Use the helper functions in `src/core/analytics.py`:

```python
from core.analytics import (
    get_user_ai_stats,
    get_job_ai_stats,
    get_daily_ai_usage,
    get_model_usage_breakdown,
)

# Get user statistics for the last 30 days
stats = await get_user_ai_stats(user_id=1, days=30)
# Returns: total_requests, total_tokens, total_cost_usd, cache_hit_rate, etc.

# Get statistics for a specific job
job_stats = await get_job_ai_stats(job_id=123)
# Returns: breakdown by function, total cost, avg duration, etc.

# Get daily usage trends
daily = await get_daily_ai_usage(user_id=1, days=30)
# Returns: list of {date, requests, tokens, cost}

# Get usage by model
models = await get_model_usage_breakdown(user_id=1, days=30)
# Returns: list of {model, requests, tokens, cost}
```

## How It Works

### 1. Explicit Context Passing
The `user_id` and `job_id` are passed explicitly through the pipeline context (`TaskContext`) and into each AI function call. This approach works correctly in distributed task queues where context variables cannot propagate across process boundaries.

Each AI function accepts `user_id` and `job_id` as optional parameters:

```python
@ai_checkpoint
async def generate_captions(
    video_path: str, 
    user_id: int | None = None, 
    job_id: int | None = None
) -> list[Caption]:
    # ... make API call ...
    
    # Tracking with explicit IDs
    await track_ai_request(
        function_name="generate_captions",
        model="whisper-1",
        user_id=user_id,
        job_id=job_id,
        prompt_tokens=500,
        completion_tokens=0,
        duration_ms=2341,
    )
```

Pipeline stages extract these from the `TaskContext` and pass them to AI functions:

```python
ctx = TaskContext.from_dict(data)
user_id = ctx.user_id
job_id = ctx.job_id

captions = await generate_captions(video_path, user_id=user_id, job_id=job_id)
```
### 2. Request Tracking
The `@ai_checkpoint` decorator automatically tracks all AI requests. It extracts `user_id` and `job_id` from the function's keyword arguments and passes them to the tracking function:

```python
@ai_checkpoint
async def generate_captions(video_path: str, user_id: int | None = None, job_id: int | None = None):
    # The decorator extracts user_id and job_id from kwargs
    # ... make API call ...
    
    # Tracking happens with the extracted IDs
    await track_ai_request(
        function_name="generate_captions",
        model="whisper-1",
        user_id=user_id,  # From kwargs
        job_id=job_id,     # From kwargs
        prompt_tokens=500,
        completion_tokens=0,
        duration_ms=2341,
    )
```

### 3. Cache Handling
Cached requests are also tracked but with:
- `cached=True`
- `model="cached"`
- `prompt_tokens=0` and `completion_tokens=0`
- `estimated_cost_usd=0.00`

This allows you to see the cache hit rate and measure time saved.

## Migration

After pulling these changes, run:

```bash
uv run python manage.py makemigrations
uv run python manage.py migrate
```

This will create the `ai_requests` table with appropriate indexes.

## Future Enhancements

Potential improvements:
1. **Real-time cost alerts** - Notify users when they exceed a cost threshold
2. **Budget limits** - Allow users to set spending limits
3. **Detailed charts** - Add time-series graphs for usage trends
4. **Export functionality** - Download CSV reports for accounting
5. **Per-feature cost breakdown** - Track costs by handout type (Excel, Vignette, Mindmap)
6. **Actual billing integration** - Fetch real costs from OpenAI API if available
7. **Cost optimization suggestions** - Recommend using faster models or caching
