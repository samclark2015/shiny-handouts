import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, cast


@dataclass
class Progress:
    """Class to represent progress of a pipeline stage."""

    message: str
    complete: float


class PipelineFailure(Exception):
    def __init__(self, message: str, stage: str | None = None):
        self.message = message
        self.stage = stage


class Pipeline[PipelineIn, PipelineOut = PipelineIn]:
    def __init__(self, callback: Callable[["Pipeline", Progress], None] | None = None):
        self._stages: list[
            Callable[["Pipeline", PipelineOut], Any | Awaitable[Any]]
        ] = []
        self._callback = callback
        self._current_stage: int | None = None

    def _wrap_sync(
        self, stage: Callable[["Pipeline", PipelineOut], Any]
    ) -> Callable[["Pipeline", PipelineOut], Awaitable[Any]]:
        """
        Wrap a synchronous stage to ensure it can be awaited.
        """

        async def wrapped_stage(pipeline: Pipeline, data: PipelineOut) -> Any:
            return await asyncio.get_event_loop().run_in_executor(
                None, stage, pipeline, data
            )

        wrapped_stage.__name__ = stage.__name__

        return wrapped_stage

    def add_stage[StageOut](
        self, stage: Callable[["Pipeline", PipelineOut], StageOut | Awaitable[StageOut]]
    ) -> "Pipeline[PipelineIn, StageOut]":
        """
        Add a stage to the pipeline that transforms the current output type TOutput to type U.
        Returns a new Pipeline that still accepts TInput but outputs U.
        """
        if not asyncio.iscoroutinefunction(stage):
            stage = self._wrap_sync(stage)
        self._stages.append(stage)
        return cast(Pipeline[PipelineIn, StageOut], self)

    async def run(self, data: PipelineIn) -> PipelineOut | PipelineFailure:
        """
        Run the pipeline with the given input data.
        Returns the final output after all stages have been applied.
        """
        current_data: Any = data
        for i, stage in enumerate(self._stages):
            try:
                self._current_stage = i
                current_data = await stage(self, current_data)
            except PipelineFailure as e:
                return e
            except Exception as e:
                return PipelineFailure(f"Error in stage {stage.__name__}: {e}")
            finally:
                self._current_stage = None
        self._current_stage = len(self._stages)
        self.report_progress("Complete")
        return current_data

    def report_progress(self, message: str, progress: float | None = None) -> None:
        """Report progress to the callback."""

        if self._callback is None or self._current_stage is None:
            return

        current = self._current_stage
        total = len(self._stages)

        complete = current / total

        if progress is not None:
            complete += 1.0 / total * progress

        if self._callback:
            self._callback(self, Progress(message, complete))

    def set_callback(self, callback: Callable[["Pipeline", Progress], None]) -> None:
        self._callback = callback


if __name__ == "__main__":

    async def parse_int(pipeline, data: str) -> int:
        """Convert string to integer"""
        return int(data)

    async def int_to_float(pipeline, data: int) -> float:
        """Convert integer to float"""
        return float(data)

    # Create a pipeline starting with str input type and str output type (no stages yet)
    # The type evolves as we add stages: Pipeline[str, str] -> Pipeline[str, int] -> Pipeline[str, float]
    pipe = (
        Pipeline[str]()
        .add_stage(parse_int)  # Pipeline[str, int]
        .add_stage(int_to_float)  # Pipeline[str, float]
    )

    # Example usage
    async def main():
        result = await pipe.run("42")  # Takes str input, returns float output
        print(f"Result: {result}, Type: {type(result)}")

    # Uncomment to run the example:
    # asyncio.run(main())
