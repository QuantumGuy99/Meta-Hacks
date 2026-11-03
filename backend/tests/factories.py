"""Shared test builders: the quiet-streak sample problem, scripted analyses, a fake model and a bare runtime."""

import json
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from crucible.contracts.common import Phase, Session, SessionConfig
from crucible.contracts.report import CodingExtra
from crucible.engine.hub import SessionRuntime
from crucible.engine.store import MemoryStore

FIXTURES = Path(__file__).resolve().parent / "fixtures"

QUIET_STREAK_REFERENCE = """\
def longest_quiet_streak(readings: list[int], threshold: int) -> int:
    best = cur = 0
    for r in readings:
        cur = cur + 1 if r < threshold else 0
        best = max(best, cur)
    return best
"""
QUIET_STREAK_STATEMENT = (
    "A library's noise sensor logs one reading a minute. Return the longest run below `threshold`."
)


def write_quiet_streak(root: Path) -> Path:
    """The quiet-streak sample as a problem folder under `root` (a stand-in until the gold problems land)."""
    folder = root / "quiet-streak"
    folder.mkdir(parents=True)
    (folder / "problem.json").write_text(
        (FIXTURES / "problem_spec.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (folder / "statement.md").write_text(QUIET_STREAK_STATEMENT, encoding="utf-8")
    (folder / "reference.py").write_text(QUIET_STREAK_REFERENCE, encoding="utf-8")
    return folder


def analysis(
    s1: str = "not_started",
    s2: str = "in_progress",
    *,
    proposal: bool = True,
    confidence: float = 0.8,
    text: str = "Before you go further, what should an empty list give you?",
    level: str = "question",
) -> dict[str, Any]:
    """An `Analysis` for quiet-streak. By default s1 (clarify the input) is missed while s2 is under way, and the
    analyzer proposes asking about it (missed steps are asked as questions, §9.5)."""
    return {
        "steps": [
            {"step_id": "s1", "status": s1, "evidence": "no mention of the empty list"},
            {"step_id": "s2", "status": s2, "evidence": "for r in readings:"},
        ],
        "issues": [],
        "stated_plan": "Walk the list once with a running count.",
        "plan_matches_code": True,
        "chosen_approach": "single pass with a running count",
        "explanation_quality": "ok",
        "proposal": {
            "trigger": "missed_step",
            "level": level,
            "step_id": "s1",
            "text": text,
            "confidence": confidence,
        }
        if proposal
        else None,
    }


FAKE_MODEL_ID = "fake-model"


class FakeModel:
    """Answers `complete_json` from a script; the last reply repeats. An Exception reply is raised."""

    def __init__(self, *replies: dict[str, Any] | Exception) -> None:
        self.replies = list(replies)
        self.calls: list[Sequence[Mapping[str, Any]]] = []

    async def complete_json[T: BaseModel](
        self,
        role: str,
        messages: Sequence[Mapping[str, Any]],
        schema: type[T],
        *,
        session_id: str | None = None,
    ) -> T:
        self.calls.append(messages)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return schema.model_validate(reply)

    async def complete_json_with_model[T: BaseModel](
        self,
        role: str,
        messages: Sequence[Mapping[str, Any]],
        schema: type[T],
        *,
        session_id: str | None = None,
    ) -> tuple[T, str]:
        return await self.complete_json(role, messages, schema, session_id=session_id), FAKE_MODEL_ID


class StubController:
    def allowed_transitions(self) -> dict[Phase, set[Phase]]:
        return {}

    async def on_start(self, rt: SessionRuntime) -> None:
        return None

    async def on_resume(self, rt: SessionRuntime) -> None:
        return None

    async def on_client_message(self, rt: SessionRuntime, msg: object) -> bool:
        return False

    async def on_timeline(self, rt: SessionRuntime, event: object) -> None:
        return None

    async def report_extra(self, rt: SessionRuntime) -> CodingExtra:
        return CodingExtra(problem_slug="", steps=[], approach=None, complexity_answer_ok=None)


def runtime(
    model: FakeModel | None = None,
    *,
    feedback: str = "active",
    monotonic: Callable[[], float] = time.monotonic,
) -> SessionRuntime:
    """A started coding runtime in `clarify`, with no sockets. Pass `monotonic` to drive its clock."""
    now = datetime.now(UTC)
    session = Session(
        id="s1",
        config=SessionConfig(mode="coding", feedback=feedback),
        phase=Phase.CLARIFY,
        created_at=now,
        started_at=now,
        ended_at=None,
        time_limit_s=1200,
        problem_slug="quiet-streak",
        project_id=None,
    )
    return SessionRuntime(
        session,
        StubController(),
        MemoryStore(),
        monotonic=monotonic,
        wall=lambda: datetime.now(UTC),
        model=model,
    )


def problem_json() -> dict[str, Any]:
    return json.loads((FIXTURES / "problem_spec.json").read_text(encoding="utf-8"))
