import asyncio
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from process import Processor
import traceback as tb

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


def worker(filename: str):
    try:
        print(f"Processing {filename}...")
        processor = Processor(filename, True)
        asyncio.run(processor.generate())
        print(f"Done processing {filename}.")
    except Exception as e:
        tb.print_exception(e)

def main():
    with ThreadPoolExecutor(max_workers=args.n) as executor:
        executor.map(worker, args.files)

if __name__ == "__main__":
    main()