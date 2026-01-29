import asyncio as aio

from nicegui import binding
from nicegui import observables as obs

from components.files import files_component
from pipeline.pipeline import Pipeline, PipelineFailure, Progress
from pipeline.process import ProcessingInput, create_pipeline


@binding.bindable_dataclass
class Task:
    label: str
    status: str = "Initialized"
    progress: float = 0.0

    _aio_task: aio.Task | None = None

    def callback(self, _: Pipeline, progress: Progress):
        print(f"Progress: {progress.message} ({progress.complete * 100:.2f}%)")
        self.progress = int(progress.complete * 100)
        self.status = progress.message

    def when_complete(self, aio_task: aio.Task):
        files_component.refresh()

        try:
            result = aio_task.result()
            if result:
                if isinstance(result, PipelineFailure):
                    self.status = f"Error: {result}"
                else:
                    global_state.tasks.remove(self)
        except aio.CancelledError:
            pass

    def run(self, pipeline_input: ProcessingInput):
        pipeline = create_pipeline(self.callback)
        global_state.tasks.append(self)
        self._aio_task = aio_task = aio.create_task(pipeline.run(pipeline_input))
        aio_task.add_done_callback(self.when_complete)

    def remove(self):
        if self._aio_task:
            self._aio_task.cancel("Cancelled by user")
        global_state.tasks.remove(self)


@binding.bindable_dataclass
class GlobalState:
    tasks = obs.ObservableList()


global_state = GlobalState()
