import os
from pathlib import Path

from nicegui import app

data_path = Path(__file__).parent / "data"


def initialize():
    # Initialize the app here
    # For example, set up database connections, load models, etc.
    if not data_path.exists():
        data_path.mkdir(parents=True)
        data_path.joinpath("output").mkdir(parents=True)

    os.makedirs("data/input", exist_ok=True)
    os.makedirs("data/output", exist_ok=True)
    os.makedirs("data/frames", exist_ok=True)

    app.add_static_files("/data", "./data")
    app.add_static_file(local_file="./userscript.js", url_path="/userscript.js")

    print("* App initialized")
