import asyncio
import pathlib
from pprint import pprint
from urllib.parse import parse_qs, urlparse

from shiny import reactive
from shiny import ui as core_ui
from shiny.express import app_opts, input, render, session, ui

from helpers import Progress
from process import PanoptoProcessor, Processor

import time

import platform
import os
import subprocess

def get_system_info():
    info = {}
    info['system'] = platform.system()
    info['node'] = platform.node()
    info['release'] = platform.release()
    info['version'] = platform.version()
    info['machine'] = platform.machine()
    info['processor'] = platform.processor()
    info['os_name'] = os.name
    if os.name == 'nt': # For Windows
        info['system_info'] = subprocess.check_output('systeminfo').decode('utf-8')
    elif os.name == 'posix': # For Linux and macOS
        info['system_info'] = subprocess.check_output(['uname', '-a']).decode('utf-8')
    return info


print("System Information:")
system_info = get_system_info()
pprint(get_system_info())
print("Environment Variables:")
pprint(dict(os.environ))

data_path = pathlib.Path(__file__).parent / "data"

if not data_path.exists():
    data_path.mkdir(parents=True)
    data_path.joinpath("output").mkdir(parents=True)

static_assets = {"/data": data_path}

app_opts(static_assets=static_assets)

loop = asyncio.get_event_loop()

html_path = reactive.value(None)

ui.page_opts(title="Lecture Downloader", fillable=False)

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
        _ = html_path()
        output_path = data_path / "output"
        files = sorted(output_path.iterdir(), key=lambda x: x.stat(follow_symlinks=True).st_ctime, reverse=True)
            
        return [
            ui.a(f"{item.stem} (created {time.strftime('%-m/%-d/%Y %-I:%M %p', time.localtime(item.stat(follow_symlinks=True).st_ctime))})", href=f"data/output/{item.name}")
            for item in files
        ]
    
    @render.download(filename="userscript.js", label="Download Userscript for TamperMonkey")
    def download_userscript():
        return "userscript.js"



@reactive.effect
@reactive.event(input.generate_handout)
async def generate_handout():
    query = query_params()

    with ui.Progress() as p:
        p.set(0, "Preparing...")

        async def async_callback(progress_value: Progress):
            p.set(
                progress_value.complete / progress_value.total,
                message="Generating...",
                detail=progress_value.stage,
            )

        def callback(progress_value: Progress):
            loop.create_task(async_callback(progress_value))

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
        html_out = await processor.generate()
        html_path.set(html_out)
