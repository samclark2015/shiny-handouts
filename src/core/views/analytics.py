"""
Analytics views for AI request tracking and cost analysis.
"""

from asgiref.sync import async_to_sync
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from core.analytics import get_all_users_overview, get_function_usage_breakdown, get_user_ai_stats


@login_required
def analytics_dashboard(request):
    """Display AI usage analytics - overview for staff, personal for regular users."""
    from accounts.models import User

    days = int(request.GET.get("days", 30))
    selected_user_id = request.GET.get("user_id")

    # Staff users can see all users or drill down into a specific user
    if request.user.is_staff:
        if selected_user_id:
            # Detail view for a specific user
            try:
                user_id = int(selected_user_id)
                stats = async_to_sync(get_user_ai_stats)(user_id, days=days)
                function_breakdown = async_to_sync(get_function_usage_breakdown)(user_id, days=days)

                # Get user info for display

                selected_user = User.objects.get(id=user_id)

                context = {
                    "is_staff_view": True,
                    "is_detail_view": True,
                    "selected_user": selected_user,
                    "stats": stats,
                    "function_breakdown": function_breakdown,
                    "days": days,
                }
            except (ValueError, User.DoesNotExist):
                # Invalid user_id, fall back to overview
                users_overview = async_to_sync(get_all_users_overview)(days=days)
                context = {
                    "is_staff_view": True,
                    "is_detail_view": False,
                    "users_overview": users_overview,
                    "days": days,
                }
        else:
            # Overview of all users
            users_overview = async_to_sync(get_all_users_overview)(days=days)
            context = {
                "is_staff_view": True,
                "is_detail_view": False,
                "users_overview": users_overview,
                "days": days,
            }
    else:
        # Regular users see only their own stats
        user_id = request.user.id
        stats = async_to_sync(get_user_ai_stats)(user_id, days=days)
        function_breakdown = async_to_sync(get_function_usage_breakdown)(user_id, days=days)

        context = {
            "is_staff_view": False,
            "is_detail_view": False,
            "stats": stats,
            "function_breakdown": function_breakdown,
            "days": days,
        }

    return render(request, "analytics/dashboard.html", context)
