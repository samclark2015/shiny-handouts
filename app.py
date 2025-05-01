import asyncio
import pathlib
import time
from urllib.parse import parse_qs, urlparse

from shiny import reactive
from shiny import ui as core_ui
from shiny.express import app_opts, input, render, session, ui

from startup import initialize
from helpers import Progress
from process import PanoptoProcessor, Processor

data_path = pathlib.Path(__file__).parent / "data"

initialize(data_path)
app_opts(static_assets={"/data": data_path})
ui.page_opts(title="Lecture Downloader")

loop = asyncio.get_event_loop()

@reactive.calc
def query_params():
    query_str = session.clientdata.url_search()
    if query_str.startswith("?"):
        query_str = query_str[1:]
    return parse_qs(query_str)


with ui.layout_columns(col_widths=[12]):
    @render.ui
    def header():
        query = query_params()
        if "cookie" in query and "url" in query:
            return core_ui.h4("Panopto Video Provided", align="center")
        else:
            return core_ui.layout_columns(
                core_ui.input_text(
                    "video_file",
                    "Video File",
                    placeholder="Paste the video URL here",
                    width="100%",
                ),
                core_ui.input_file(
                    "video_file_upload",
                    "Upload Video File",
                    multiple=False,
                    width="100%",
                    accept=".mp4",
                ),
                col_widths=[6, 6],
            )

    ui.input_task_button("generate_handout", "Generate Handout")

    @render.ui
    def links():
        return [
            ui.a(
                f"{item.stem} (created {time.strftime('%-m/%-d/%Y %-I:%M %p', time.localtime(item.stat(follow_symlinks=True).st_ctime))})",
                href=f"data/output/{item.name}",
            )
            for item in file_list()
        ]

    @render.download(
        filename="userscript.js", label="Download Userscript for TamperMonkey"
    )
    def download_userscript():
        return "userscript.js"

@reactive.calc
def file_list():
    output_path = data_path / "output"
    files = sorted(
        output_path.iterdir(),
        key=lambda x: x.stat(follow_symlinks=True).st_ctime,
        reverse=True,
    )
    return files

def get_processor(callback) -> Processor:
    query = query_params()
        
    if "cookie" in query and "url" in query:
        cookie = query["cookie"][0]
        url = query["url"][0]
        parts = urlparse(url)
        qs = parse_qs(parts.query)
        delivery_id, *_ = qs.get("id", [""])

        base = f"{parts.scheme}://{parts.netloc}"
        processor = PanoptoProcessor(
            base=base,
            cookie=cookie,
            delivery_id=delivery_id,
            use_ai=True,
            callback=callback,
        )
    else:
        video_path = input.video_file()

        if not video_path:
            video_path = input.video_file_upload()
            if not video_path:
                ui.show_notification("Please provide a video file.")
                return
            video_path = video_path[0]["datapath"]
        processor = Processor(video_path, use_ai=True, callback=callback)

    return processor

@reactive.effect
@reactive.event(input.generate_handout)
async def generate_handout():
    with ui.Progress() as progress:
        progress.set(0, message="Processing...", detail="Initializing")
        async def callback(progress_value: Progress):
            progress.set(
                progress_value.complete / progress_value.total,
                message="Processing...",
                detail=progress_value.stage,
            )

        try:
            processor = get_processor(lambda progress: loop.create_task(callback(progress)))
        except Exception as e:
            ui.notification_show(f"Error Processing ({e})", type="error", duration=None)
            return

        try:
            await processor.generate()
        except Exception as e:
            ui.notification_show(f"Error Processing ({e})", type="error", duration=None)
            processor.abort()
            return
        
        ui.notification_show("Handout generated successfully", duration=5, type="message")
        # Update the file list
        await file_list.update_value()
        ui.update_text("video_file", value="")
        ui.update_text("video_file_upload", value="")
