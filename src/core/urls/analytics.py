"""
URL configuration for analytics views.
"""

from django.urls import path

from core.views.analytics import analytics_dashboard

urlpatterns = [
    path("", analytics_dashboard, name="analytics_dashboard"),
]
