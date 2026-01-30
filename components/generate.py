from urllib.parse import parse_qs, urlparse

from nicegui import binding, events, ui

from pipeline.process import PanoptoInput
from startup import data_path
from state import Task


@binding.bindable_dataclass
class State:
    link: str | None = None
    upload: str | None = None
    url_cookie: tuple[str, str] | None = None

    def handle_upload(self, upload: events.UploadEventArguments):
        out = data_path / "input" / upload.name
        with open(out, "wb") as f:
            f.write(upload.content.read())
        self.upload = out.as_posix()

    @property
    def can_generate(self) -> bool:
        has_panopto = self.url_cookie is not None and len(self.url_cookie) == 2
        has_link = bool(self.link and self.link.strip())
        has_upload = bool(self.upload and self.upload.strip())
        return (has_link ^ has_upload ^ has_panopto) and (
            has_link or has_upload or has_panopto
        )

    def generate(self):
        if self.url_cookie:
            url, cookie = self.url_cookie

            parts = urlparse(url)
            qs = parse_qs(parts.query)
            delivery_id, *_ = qs.get("id", [""])
            base = f"{parts.scheme}://{parts.netloc}"

            name = "Panopto Video"
            pipeline_input = PanoptoInput(base, cookie, delivery_id)
        elif self.link:
            name = self.link.split("/")[-1]
            pipeline_input = self.link
        elif self.upload:
            name = self.upload.split("/")[-1]
            pipeline_input = self.upload
        else:
            raise ValueError("No link or upload provided")

        task = Task(label=name)

        task.run(pipeline_input)


def generate_component(cookie: str | None = None, url: str | None = None):
    state = State(url_cookie=(url, cookie) if cookie and url else None)
    with ui.column(align_items="center").classes("w-full"):
        with ui.row(align_items="center").classes("w-full"):
            is_panopto = bool(cookie and url)
            if is_panopto:
                ui.label("Generating handout from Panopto video")
                link_input = None
                upload = None
            else:
                link_input = (
                    ui.input(label="Link to Video")
                    .bind_value(state, "link")
                    .classes("flex-1")
                )
                ui.label("or").classes("mx-2")
                upload = (
                    ui.upload(
                        label="Upload Video File",
                        auto_upload=True,
                        multiple=False,
                        max_files=1,
                    )
                    .props("accept='.mp4'")
                    .on_upload(lambda e: state.handle_upload(e))
                    .classes("flex-1")
                )

        def handle_generate():
            if not state.can_generate:
                ui.notify("Please provide a link or upload a file.", color="red")
                return
            state.generate()
            if link_input:
                link_input.set_value("")
            if upload:
                upload.reset()

        ui.button("Generate").bind_enabled_from(state, "can_generate").on_click(
            handle_generate
        )
