from nicegui import app, ui

from auth import logout
from components.files import files_component
from components.generate import generate_component
from components.tasks import tasks_component
from state import global_state


@ui.page("/")
def index(cookie: str | None = None, url: str | None = None):
    with ui.header():
        ui.label("Lecture Downloader").classes("text-2xl font-bold grow")
        if app.storage.user.get("user_data"):
            name = app.storage.user["user_data"]["userinfo"]["name"]
            with ui.row(align_items="center"):
                ui.label(f"Logged in as {name}").classes("text-lg")
                ui.button("Logout", on_click=logout, color="goldenrod")

    with ui.column(align_items="center").classes("w-full"):
        with ui.card().classes("w-1/2 flex"):
            ui.label("Generate a Handout").classes("text-2xl font-bold mb-4")
            generate_component(cookie, url)

        with ui.card().classes("w-1/2 flex"):
            tasks_component()
            files_component()

        global_state.tasks.on_change(tasks_component.refresh)
