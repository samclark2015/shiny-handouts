"""
Analytics views for AI request tracking and cost analysis.
"""

from asgiref.sync import async_to_sync
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from core.analytics import get_function_usage_breakdown, get_user_ai_stats


@login_required
def analytics_dashboard(request):
    """Display AI usage analytics for staff users only."""
    user_id = request.user.id
    days = int(request.GET.get("days", 30))

    # Get user statistics (wrap async functions)
    stats = async_to_sync(get_user_ai_stats)(user_id, days=days)
    function_breakdown = async_to_sync(get_function_usage_breakdown)(user_id, days=days)

    context = {
        "stats": stats,
        "function_breakdown": function_breakdown,
        "days": days,
    }

    return render(request, "analytics/dashboard.html", context)
