"""
Analytics utilities for AI request tracking and cost analysis.
"""

from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate

# Mapping of internal function names to user-friendly display names
FUNCTION_DISPLAY_NAMES = {
    "generate_captions": "Caption Extraction",
    "clean_transcript": "Transcript Cleanup",
    "gen_keypoints": "Keypoint Generation",
    "generate_title": "Title Generation",
    "generate_spreadsheet_helper": "Study Table (Excel)",
    "generate_vignette_questions": "Vignette Questions",
    "generate_mindmap": "Mindmap Generation",
}


async def get_user_ai_stats(user_id: int, days: int = 30):
    """Get AI usage statistics for a user over the past N days."""
    from datetime import timedelta

    from django.utils import timezone

    from .models import AIRequest

    cutoff_date = timezone.now() - timedelta(days=days)

    stats = await AIRequest.objects.filter(
        user_id=user_id,
        created_at__gte=cutoff_date,
    ).aaggregate(
        total_requests=Count("id"),
        total_tokens=Sum("total_tokens"),
        total_cost=Sum("estimated_cost_usd"),
        cached_requests=Count("id", filter=Q(cached=True)),
        failed_requests=Count("id", filter=Q(success=False)),
    )

    # Calculate cache hit rate
    total = stats["total_requests"] or 0
    cached = stats["cached_requests"] or 0
    cache_hit_rate = (cached / total * 100) if total > 0 else 0

    return {
        "total_requests": total,
        "total_tokens": stats["total_tokens"] or 0,
        "total_cost_usd": stats["total_cost"] or Decimal("0.00"),
        "cached_requests": cached,
        "failed_requests": stats["failed_requests"] or 0,
        "cache_hit_rate": round(cache_hit_rate, 2),
        "days": days,
    }


async def get_job_ai_stats(job_id: int):
    """Get AI usage statistics for a specific job."""
    from .models import AIRequest

    stats = await AIRequest.objects.filter(job_id=job_id).aaggregate(
        total_requests=Count("id"),
        total_tokens=Sum("total_tokens"),
        total_cost=Sum("estimated_cost_usd"),
        cached_requests=Count("id", filter=Q(cached=True)),
        failed_requests=Count("id", filter=Q(success=False)),
        avg_duration_ms=Sum("duration_ms") / Count("id", filter=Q(duration_ms__isnull=False)),
    )

    # Get breakdown by function
    functions = (
        AIRequest.objects.filter(job_id=job_id)
        .values("function_name", "model")
        .annotate(
            count=Count("id"),
            tokens=Sum("total_tokens"),
            cost=Sum("estimated_cost_usd"),
        )
        .order_by("-cost")
    )

    function_breakdown = [f async for f in functions]

    return {
        "total_requests": stats["total_requests"] or 0,
        "total_tokens": stats["total_tokens"] or 0,
        "total_cost_usd": stats["total_cost"] or Decimal("0.00"),
        "cached_requests": stats["cached_requests"] or 0,
        "failed_requests": stats["failed_requests"] or 0,
        "avg_duration_ms": stats["avg_duration_ms"] or 0,
        "function_breakdown": function_breakdown,
    }


async def get_daily_ai_usage(user_id: int | None = None, days: int = 30):
    """Get daily AI usage breakdown."""
    from datetime import timedelta

    from django.utils import timezone

    from .models import AIRequest

    cutoff_date = timezone.now() - timedelta(days=days)

    queryset = AIRequest.objects.filter(created_at__gte=cutoff_date)
    if user_id:
        queryset = queryset.filter(user_id=user_id)

    daily_stats = (
        queryset.annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(
            requests=Count("id"),
            tokens=Sum("total_tokens"),
            cost=Sum("estimated_cost_usd"),
        )
        .order_by("date")
    )

    return [s async for s in daily_stats]


async def get_function_usage_breakdown(user_id: int | None = None, days: int = 30):
    """Get usage breakdown by function name."""
    from datetime import timedelta

    from django.utils import timezone

    from .models import AIRequest

    cutoff_date = timezone.now() - timedelta(days=days)

    queryset = AIRequest.objects.filter(created_at__gte=cutoff_date)
    if user_id:
        queryset = queryset.filter(user_id=user_id)

    function_stats = (
        queryset.values("function_name")
        .annotate(
            requests=Count("id"),
            tokens=Sum("total_tokens"),
            cost=Sum("estimated_cost_usd"),
        )
        .order_by("-cost")
    )

    # Add display names to the results
    results = []
    async for stat in function_stats:
        function_name = stat["function_name"]
        stat["display_name"] = FUNCTION_DISPLAY_NAMES.get(function_name, function_name)
        results.append(stat)

    return results
