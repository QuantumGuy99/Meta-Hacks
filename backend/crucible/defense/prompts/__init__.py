"""Defense prompts, loaded once from *.md (PLAN §22 rule 4). The first `# heading` is the key."""

from __future__ import annotations

from pathlib import Path


def _load() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(Path(__file__).parent.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        first, _, body = text.partition("\n")
        out[first.removeprefix("#").strip()] = body.strip()
    return out


PROMPTS = _load()
