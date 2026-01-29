import asyncio
import traceback as tb
from argparse import ArgumentParser

from pipeline.process import PanoptoInput, create_pipeline

parser = ArgumentParser()
parser.add_argument("--download", action="store_true", help="Download the video only")

parser.add_argument(
    "-n",
    default=5,
    type=int,
    help="Number of threads to use for processing. Default is 5.",
)
parser.add_argument(
    "--files",
    nargs="+",
    help="Path to the video file or URL. If not provided, it will be downloaded.",
)
parser.add_argument("--base", help="Panopto base URL")
parser.add_argument("--cookie", help="Panopto cookie")
parser.add_argument("--delivery-id", help="Panopto delivery ID")
args = parser.parse_args()

if not args.files:
    if not (args.base and args.cookie and args.delivery_id):
        parser.error(
            "You must provide either --files, or all of --base, --cookie, and --delivery-id."
        )
    pipeline_input: list[str] | PanoptoInput = PanoptoInput(
        args.base, args.cookie, args.delivery_id
    )
else:
    if args.base or args.cookie or args.delivery_id:
        parser.error(
            "When --files is provided, do not specify --base, --cookie, or --delivery-id."
        )
    pipeline_input: list[str] | PanoptoInput = list(args.files)


sem = asyncio.Semaphore(args.n)


def callback(pipeline, progress):
    print("Progress:", progress)


async def worker(filename: str | PanoptoInput):
    try:
        print(f"Processing {filename}...")
        pipeline = create_pipeline(callback=callback)
        async with sem:
            await pipeline.run(filename, throw=True)
        print(f"Done processing {filename}.")
    except Exception as e:
        tb.print_exception(e)

async def main():
    if isinstance(pipeline_input, list):
        await asyncio.gather(*(worker(f) for f in pipeline_input))
    else:
        await worker(pipeline_input)

if __name__ == "__main__":
    asyncio.run(main())