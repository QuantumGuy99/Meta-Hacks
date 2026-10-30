"""Data-tool prompts, loaded once at import (PLAN §22 rule 4). The key is the file name without `.md`."""

from pathlib import Path

PROMPTS: dict[str, str] = {path.stem: path.read_text() for path in sorted(Path(__file__).parent.glob("*.md"))}
