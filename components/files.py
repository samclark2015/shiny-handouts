import time

from nicegui import ui

from startup import data_path


@ui.refreshable
def files_component():
    output_path = data_path / "output"
    files = sorted(
        output_path.iterdir(),
        key=lambda x: x.stat(follow_symlinks=True).st_ctime,
        reverse=True,
    )
    with ui.column().classes("w-full"):
        for file in files:
            ext = file.suffix.lower()
            match ext:
                case ".pdf":
                    file_type = "PDF"
                case ".xlsx" | ".xls":
                    file_type = "Excel"
                case x:
                    file_type = x.upper()
            ui.link(
                f"{file.stem} ({file_type}) (created {time.strftime('%-m/%-d/%Y %-I:%M %p', time.localtime(file.stat(follow_symlinks=True).st_ctime))})",
                target=f"data/output/{file.name}",
                new_tab=True,
            )
            ui.separator()
