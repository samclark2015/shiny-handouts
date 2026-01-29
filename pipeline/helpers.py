from collections import namedtuple
from pathlib import Path

import requests

Caption = namedtuple("Caption", ("text", "timestamp"))
Slide = namedtuple("Slide", ("image", "caption", "extra"))
Progress = namedtuple("Progress", ("stage", "complete", "total"))

# Prompts directory
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def read_prompt(name: str) -> str:
    """Read a prompt from the prompts directory."""
    prompt_path = PROMPTS_DIR / f"{name}.md"
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def fetch(base: str, cookie: str, url: str, params: dict[str, str] = {}):
    return requests.get(
        f"{base}/{url}", cookies={".ASPXAUTH": cookie}, params=params
    ).json()
