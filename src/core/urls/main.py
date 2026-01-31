"""Main URL patterns for the core app."""

from django.urls import path

from core.views import api, main

app_name = "main"

urlpatterns = [
    path("", main.index, name="index"),
    path("files/<path:filename>", main.serve_file, name="serve_file"),
    path("bug-report/", api.submit_bug_report, name="submit_bug_report"),
]
