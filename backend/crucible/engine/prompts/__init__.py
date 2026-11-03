"""Engine prompts, loaded once at import (PLAN §22 rule 4). The key is the file name without `.md`."""

from pathlib import Path

PROMPTS: dict[str, str] = {
    path.stem: path.read_text(encoding="utf-8") for path in sorted(Path(__file__).parent.glob("*.md"))
}


def line_entries(text: str) -> dict[str, str]:
    """The `- key: text` lines of a canned-lines file (also used by coding/prompts)."""
    pairs = (line[2:].partition(": ") for line in text.splitlines() if line.startswith("- "))
    return {key.strip(): value.strip() for key, sep, value in pairs if sep}


# The interviewer's fallback line per trigger, plus `concept` (canned.md, PLAN §9.6).
CANNED: dict[str, str] = line_entries(PROMPTS["canned"])
