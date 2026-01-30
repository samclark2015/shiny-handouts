import re
from collections import namedtuple
from pathlib import Path

import requests
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont

Caption = namedtuple("Caption", ("text", "timestamp"))
Slide = namedtuple("Slide", ("image", "caption", "extra"))
Progress = namedtuple("Progress", ("stage", "complete", "total"))

# Prompts directory - now relative to src
PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


def read_prompt(name: str) -> str:
    """Read a prompt from the prompts directory."""
    prompt_path = PROMPTS_DIR / f"{name}.md"
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def fetch(base: str, cookie: str, url: str, params: dict[str, str] = {}):
    return requests.get(
        f"{base}/{url}", cookies={".ASPXAUTH": cookie}, params=params
    ).json()


def parse_markdown_bold_to_rich_text(text: str) -> CellRichText | str:
    """
    Parse Markdown bold syntax (**text**) and convert to Excel rich text.
    Returns CellRichText if bold markers are found, otherwise returns the original string.
    """
    if not text or not isinstance(text, str):
        return text or ""

    # Pattern to match **bold** text
    pattern = r"\*\*(.+?)\*\*"

    # Check if there are any bold markers
    if not re.search(pattern, text):
        return text

    # Split text into parts (bold and non-bold)
    parts = []
    last_end = 0

    for match in re.finditer(pattern, text):
        # Add non-bold text before this match
        if match.start() > last_end:
            non_bold_text = text[last_end : match.start()]
            if non_bold_text:
                parts.append(non_bold_text)

        # Add bold text
        bold_text = match.group(1)
        if bold_text:
            bold_font = InlineFont(b=True)
            parts.append(TextBlock(bold_font, bold_text))

        last_end = match.end()

    # Add any remaining non-bold text after the last match
    if last_end < len(text):
        remaining_text = text[last_end:]
        if remaining_text:
            parts.append(remaining_text)

    # Return CellRichText if we have parts, otherwise original text
    if parts:
        return CellRichText(parts)
    return text
