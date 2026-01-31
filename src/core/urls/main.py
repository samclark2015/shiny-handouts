"""Main URL patterns for the core app."""

from django.urls import path

from core.views import api, main

app_name = "main"

urlpatterns = [
    path("", main.index, name="index"),
    path("files/<path:filename>", main.serve_file, name="serve_file"),
    path("mindmap/<path:filename>", main.render_mindmap, name="render_mindmap"),
    path("lecture/<int:lecture_id>/mindmaps/", main.lecture_mindmaps, name="lecture_mindmaps"),
    path("bug-report/", api.submit_bug_report, name="submit_bug_report"),
]
