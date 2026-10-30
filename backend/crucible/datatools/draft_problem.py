"""Draft a problem with the `drafter` model into data/problems/_drafts/ (DATA-2, PLAN §13.1).

    uv run python -m crucible.datatools.draft_problem --pattern "sliding window" --difficulty medium

A draft never goes straight into the bank: run validate_problems --drafts <slug>, do the human review
(quality bar + originality, PLAN §22 rule 13), then move the folder out of _drafts/ yourself.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from pydantic import ValidationError

from crucible.coding.problems import DEFAULT_ROOT
from crucible.config import get_settings
from crucible.contracts.coding import ProblemSpec
from crucible.datatools.prompts import PROMPTS

DRAFTS = DEFAULT_ROOT / "_drafts"
TEMPLATE = DEFAULT_ROOT / "_template" / "problem.json"
DRAFT_TIMEOUT_S = 180  # the drafter's 120 s plus one fallback model (registry)
SIBLING_FILES = {
    "statement_md": "statement.md",
    "reference_py": "reference.py",
    "brute_py": "brute.py",
    "gen_py": "gen.py",
}
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){0,3}$")
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


class DraftInvalid(Exception):
    """The model's draft can't be written: bad JSON, wrong shape or an unsafe slug."""


def parse_draft(text: str) -> tuple[str, dict[str, str]]:
    """(slug, {file name: content}) from the model's reply. Checks the problem against ProblemSpec."""
    try:
        raw = json.loads(_FENCE.sub("", text.strip()))
    except json.JSONDecodeError as exc:
        raise DraftInvalid(f"the reply isn't JSON: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("problem"), dict):
        raise DraftInvalid("the reply has no `problem` object")
    missing = [k for k in SIBLING_FILES if not isinstance(raw.get(k), str)]
    if missing:
        raise DraftInvalid(f"the reply is missing {missing}")
    problem = raw["problem"]
    slug = str(problem.get("slug", ""))
    if not _SLUG.match(slug):
        raise DraftInvalid(f"unsafe or malformed slug {slug!r}")  # it becomes a folder name
    try:
        ProblemSpec.model_validate(
            {**problem, "statement_md": raw["statement_md"], "reference_solution": raw["reference_py"]}
        )
    except ValidationError as exc:
        raise DraftInvalid(f"problem.json doesn't match ProblemSpec: {exc}") from exc
    files = {"problem.json": json.dumps(problem, indent=2) + "\n"}
    files |= {name: raw[key] for key, name in SIBLING_FILES.items()}
    return slug, files


def write_draft(slug: str, files: dict[str, str], root: Path = DRAFTS) -> Path:
    folder = root / slug
    if folder.exists() or (root.parent / slug).exists():
        raise DraftInvalid(f"{slug} already exists; draft again or rename it")
    folder.mkdir(parents=True)
    for name, content in files.items():
        (folder / name).write_text(content)
    return folder


async def draft(pattern: str, difficulty: str) -> str:
    from crucible.models import llm

    messages = [
        {"role": "system", "content": PROMPTS["drafter_system"]},
        {
            "role": "user",
            "content": f"Pattern: {pattern}\nDifficulty: {difficulty}\n\nTemplate problem.json:\n{TEMPLATE.read_text()}",
        },
    ]
    async with asyncio.timeout(DRAFT_TIMEOUT_S):
        return await llm.complete_text("drafter", messages)


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m crucible.datatools.draft_problem")
    ap.add_argument("--pattern", required=True, help='e.g. "sliding window"')
    ap.add_argument("--difficulty", required=True, choices=["easy", "medium", "hard"])
    args = ap.parse_args()
    from crucible.main import _configure_models
    from crucible.models.llm import AllModelsFailed

    if _configure_models(get_settings()) is None:
        print("MODEL_API_KEY isn't set in .env; the drafter needs a Meta model", file=sys.stderr)
        return 2
    try:
        slug, files = parse_draft(asyncio.run(draft(args.pattern, args.difficulty)))
        folder = write_draft(slug, files)
    except (DraftInvalid, TimeoutError, AllModelsFailed) as exc:
        print(f"draft failed: {exc or 'the drafter timed out'}", file=sys.stderr)
        return 1
    print(f"wrote {folder}\nnext: uv run python -m crucible.datatools.validate_problems --drafts {slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
