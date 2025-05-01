from pathlib import Path


intialized = False


def initialize(data_path: Path):
    global intialized
    if intialized:
        return
    intialized = True
    # Initialize the app here
    # For example, set up database connections, load models, etc.
    if not data_path.exists():
        data_path.mkdir(parents=True)
        data_path.joinpath("output").mkdir(parents=True)

    
    print("App initialized")