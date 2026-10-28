"""Coding-mode prompt files, loaded once at import (PLAN §22 rule 4)."""

from pathlib import Path

from crucible.engine.prompts import line_entries

# The interviewer's phase lines: intro, wrap-up openers and the closing line (phase_lines.md, PLAN §9.6).
PHASE_LINES: dict[str, str] = line_entries((Path(__file__).parent / "phase_lines.md").read_text())
# What the candidate said in the complexity wrap-up answer, for the report (complexity.md, COD-5).
COMPLEXITY_PROMPT: str = (Path(__file__).parent / "complexity.md").read_text()
