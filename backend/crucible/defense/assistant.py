"""The fix assistant (DEF-11, PLAN §11.9): a Muse Spark coding assistant beside the fix stage.

The model suggests an answer and edits; code decides what reaches the editor: only files the project has, under
the file size limit, at most MAX_EDITS, and never an edit that changes nothing. Every ask, reply and apply is on
the timeline (`assistant`), so the report and replay show how much of the fix the AI wrote.
"""

from __future__ import annotations

import json
import logging

from crucible.contracts.defense import AssistantDraft, AssistantEdit, ChaosRun, Finding
from crucible.contracts.events import MAX_FILE_CHARS
from crucible.defense.ports import ModelClient
from crucible.defense.prompts import PROMPTS

logger = logging.getLogger(__name__)

ASSIST_TIMEOUT_S = 20  # PLAN §11.9; the registry's own timeout is the same
MAX_ASKS = 20  # per session: a cost guard (§11.9)
MAX_EDITS = 5
MAX_PROMPT_FILE_CHARS = 20_000  # a file longer than this goes to the model cut (projects are ≤ 6,000 lines)
UNAVAILABLE = "The assistant isn't available right now. Keep going on your own, or ask again in a moment."


async def ask_assistant(
    llm: ModelClient,
    request: str,
    files: dict[str, str],
    findings: list[Finding],
    runs: list[ChaosRun],
) -> AssistantDraft:
    """The model's answer with its edits checked. Raises ModelUnavailable (the caller says so and carries on)."""
    draft = await llm.complete_json(
        "assistant", messages(request, files, findings, runs), AssistantDraft, timeout_s=ASSIST_TIMEOUT_S
    )
    return check_draft(draft, files)


def check_draft(draft: AssistantDraft, files: dict[str, str]) -> AssistantDraft:
    """Code decides what the model's edits may touch: known files, within the size limit, real changes, once each."""
    edits: dict[str, AssistantEdit] = {}
    for edit in draft.edits:
        if edit.path not in files or len(edit.content) > MAX_FILE_CHARS:
            logger.info("assistant edit dropped: %s", edit.path[:80])
            continue
        if edit.content != files[edit.path] and edit.path not in edits:
            edits[edit.path] = edit
    return AssistantDraft(text=draft.text.strip(), edits=list(edits.values())[:MAX_EDITS])


def messages(
    request: str, files: dict[str, str], findings: list[Finding], runs: list[ChaosRun]
) -> list[dict]:
    user = {
        "findings": [
            f.model_dump(
                include={"title", "category", "file", "line_start", "line_end", "explanation", "fix_steps"}
            )
            for f in findings
        ],
        "attacks": [
            {"finding": r.finding_id, "kind": r.kind, "verdict": r.verdict, "summary": r.summary}
            for r in runs
        ],
        "files": {path: text[:MAX_PROMPT_FILE_CHARS] for path, text in files.items()},
        "request": request,
    }
    return [
        {"role": "system", "content": PROMPTS["assistant_system"]},
        {"role": "user", "content": json.dumps(user)},
    ]
