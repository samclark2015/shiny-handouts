# Handout Generator Refactor

## Description
This is a complex project composed of:

- A web frontend written in the NiceGUI framework (see pages/ and components/)
- A bespoke asynchronous processing pipeline solution (see pipeline/pipeline.py)
- Various data and AI process steps (see pipeline/process.py and pipeline/ai.py)

The general workflow is:
- User provides lecture in one of:
    - Video file, uploaded
    - Video file, URL
    - Pantopto site, various parameters
- Transcript and snapshots extracted from the provided video
- Extracted transcript is cleaned up
- Artifacts generated:
    - 16-up PDF file of lecture snapshots and transcript
    - Excel file outlining specific processes from lecture (generated using AI)
    - Quiz/vignette sampler in PDF form (generated using AI)

## Goal
Take this from a proof of concept, and make it more robust and using traditional frameworks.

### UI
Migrate from NiceGUI to a more well-supported framework. This should still be a web framework, but explore options like Django, Flask, and React for frontend. Consider other solutions if they would be better suited to the task.

Additionally, the UI should be refactored to support a nested file hierarchy (e.g. Date -> Lecture Name -> Artifacts).

### Job Management
The bespoke solution is unpredictable and hard to manage. The job management should be migrated to a solution like Celery. The new system must:
- Allow tracking/progress of jobs, for user feedback
- Be durable, allowing failed jobs to be retried upon user request
- Be cancelable, to allow users to cancel running jobs

### State Management
Present, state is tracked entirely in memory and on the filesystem. The new system should track state in a relational database. This should be configurable to use different DBs, like Postgresql, MySQL/MariaDB, or SQLite (for testing).