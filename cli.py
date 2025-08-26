import asyncio
import traceback as tb
from argparse import ArgumentParser

from pipeline.process import create_pipeline

parser = ArgumentParser()

parser.add_argument(
    "-n",
    default=5,
    type=int,
    help="Number of threads to use for processing. Default is 5.",
)
parser.add_argument(
    "files",
    nargs="+",
    help="Path to the video file or URL. If not provided, it will be downloaded.",
)
args = parser.parse_args()


sem = asyncio.Semaphore(args.n)


def callback(pipeline, progress):
    print("Progress:", progress)


async def worker(filename: str):
    try:
        print(f"Processing {filename}...")
        pipeline = create_pipeline(callback=callback)
        async with sem:
            await pipeline.run(filename)
        print(f"Done processing {filename}.")
    except Exception as e:
        tb.print_exception(e)

async def main():
    await asyncio.gather(*(worker(f) for f in args.files))


if __name__ == "__main__":
    asyncio.run(main())