"""
Analytics views for AI request tracking and cost analysis.
"""

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from core.analytics import get_model_usage_breakdown, get_user_ai_stats


@staff_member_required
async def analytics_dashboard(request):
    """Display AI usage analytics for staff users only."""
    user_id = request.user.id
    days = int(request.GET.get("days", 30))

    # Get user statistics
    stats = await get_user_ai_stats(user_id, days=days)
    model_breakdown = await get_model_usage_breakdown(user_id, days=days)

    context = {
        "stats": stats,
        "model_breakdown": model_breakdown,
        "days": days,
    }

    return render(request, "analytics/dashboard.html", context)
