from nicegui import ui

from state import global_state


@ui.refreshable
def tasks_component():
    if not global_state.tasks:
        return

    with ui.column().classes("w-full"):
        for task in global_state.tasks:
            with ui.row(align_items="center").classes("w-full"):
                ui.button("✖", on_click=lambda _, t=task: t.remove()).classes(
                    "text-red-500"
                )
                ui.label().bind_text_from(task, "label").classes("grow")
                ui.label().bind_text_from(task, "status").classes("mx-2")
                ui.circular_progress(min=0, max=100).bind_value_from(task, "progress")
                ui.separator()
