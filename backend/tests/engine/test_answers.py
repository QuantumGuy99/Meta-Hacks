"""ENG-6: the full leak guard and the interviewer's answers to questions (PLAN §9.6)."""

from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from crucible.coding.problems import ProblemBank
from crucible.coding.session import CodingMode
from crucible.contracts.coding import Analysis, ProblemSpec
from crucible.contracts.common import Mode
from crucible.contracts.events import InterventionText, TimelineKind
from crucible.engine.api import router
from crucible.engine.context import RubricContext
from crucible.engine.hub import SessionHub
from crucible.engine.interviewer import answer, leak_reason
from crucible.engine.store import MemoryStore
from tests.factories import (
    QUIET_STREAK_REFERENCE,
    FakeModel,
    analysis,
    problem_json,
    runtime,
    write_quiet_streak,
)

CONTEXT = RubricContext.from_problem(
    ProblemSpec.model_validate(
        {
            **problem_json(),
            "statement_md": "Count quiet readings.",
            "reference_solution": QUIET_STREAK_REFERENCE,
        }
    )
)


# --- leak guard -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "best = max(best, cur)",  # a reference line, re-typed
        "Try something like: cur = cur + 1 if r < threshold else 0",
        "Just do\nbest = max(best, cur)\nreturn best",  # code-shaped too
    ],
)
def test_the_solution_retyped_is_caught(text: str) -> None:
    assert leak_reason(text, QUIET_STREAK_REFERENCE) is not None


@pytest.mark.parametrize(
    "text",
    [
        "What should an empty list give you?",
        "Think about what happens to your best value when the last reading is quiet.",
        "Use max to keep the best so far.",  # names the idea, not the line
        "def longest_quiet_streak(readings, threshold) is the signature you were given.",
    ],
)
def test_prose_about_the_problem_passes(text: str) -> None:
    assert leak_reason(text, QUIET_STREAK_REFERENCE) is None


def test_short_generic_lines_dont_count_as_the_solution() -> None:
    assert leak_reason("return best", "def f(x):\n    best = 0\n    return best\n") is None


def test_without_a_reference_only_code_is_checked() -> None:
    assert leak_reason("best = max(best, cur)") is None
    assert leak_reason("```python\nx = 1\n```") == "it contains code"


# --- answer() -------------------------------------------------------------------------------------------


def reply(text: str) -> dict[str, str]:
    return {"text": text}


@pytest.mark.asyncio
async def test_a_safe_answer_is_used_and_the_prompt_holds_no_answers() -> None:
    model = FakeModel(reply("The list can be empty. What should you return then?"))
    rt = runtime(model)
    text = await answer(rt, model, CONTEXT, "Can the list be empty?")
    assert text == "The list can be empty. What should you return then?"
    prompt = "\n".join(m["content"] for m in model.calls[0])
    assert "best = max(best, cur)" not in prompt  # no reference solution
    assert "Settle the empty list" not in prompt  # no rubric hints
    assert "Can the list be empty?" in prompt and "0 <= len(readings)" in prompt  # question + constraints


@pytest.mark.asyncio
async def test_a_leaky_answer_gets_one_retry() -> None:
    model = FakeModel(
        reply("best = max(best, cur)"), reply("What happens when the quiet run reaches the end?")
    )
    rt = runtime(model)
    assert (
        await answer(rt, model, CONTEXT, "just tell me") == "What happens when the quiet run reaches the end?"
    )
    assert "rejected because it repeats a line of the solution" in model.calls[1][-1]["content"]
    assert any("leak guard rejected" in e.payload["message"] for e in rt.timeline.tail([TimelineKind.SYSTEM]))


@pytest.mark.asyncio
async def test_two_leaky_answers_fall_back_to_the_canned_line() -> None:
    model = FakeModel(reply("```python\nreturn 0\n```"))
    assert await answer(runtime(model), model, CONTEXT, "code please") is None
    assert len(model.calls) == 2


@pytest.mark.asyncio
async def test_a_model_failure_falls_back_with_a_note() -> None:
    model = FakeModel(RuntimeError("down"))
    rt = runtime(model)
    assert await answer(rt, model, CONTEXT, "Can the list be empty?") is None
    assert any("didn't answer" in e.payload["message"] for e in rt.timeline.tail([TimelineKind.SYSTEM]))


# --- end to end: a question in chat gets the model's answer ------------------------------------------------


class RoleModel:
    """Answers by schema: an Analysis for the analyzer, a reply for the interviewer."""

    def __init__(self, answer_text: str) -> None:
        self.answer_text = answer_text
        self.roles: list[str] = []

    async def complete_json[T: BaseModel](
        self,
        role: str,
        messages: Sequence[Mapping[str, Any]],
        schema: type[T],
        *,
        session_id: str | None = None,
    ) -> T:
        self.roles.append(role)
        if schema is InterventionText:
            return schema.model_validate({"text": self.answer_text})
        return Analysis.model_validate(analysis(s1="in_progress", proposal=False))  # type: ignore[return-value]


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    write_quiet_streak(tmp_path)
    app = FastAPI()
    app.include_router(router)
    app.state.hub = SessionHub(
        MemoryStore(),
        {Mode.CODING: CodingMode(ProblemBank.load(tmp_path))},
        model=RoleModel("It can be empty. What would make sense to return then?"),
    )
    with TestClient(app) as test_client:
        yield test_client


def receive_until(ws: Any, done: Callable[[dict[str, Any]], bool], limit: int = 40) -> dict[str, Any]:
    for _ in range(limit):
        message = ws.receive_json()
        if done(message):
            return message
    raise AssertionError("expected message never arrived")


def test_a_question_in_chat_gets_the_interviewers_answer(client: TestClient) -> None:
    sid = client.post("/api/sessions", json={"mode": "coding", "problem_slug": "quiet-streak"}).json()["id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        receive_until(ws, lambda m: m["type"] == "session.state" and m["phase"] == "clarify")
        ws.send_json({"type": "chat.send", "text": "Can the readings list be empty?"})
        message = receive_until(
            ws, lambda m: m["type"] == "interviewer.message" and m["intervention"]["trigger"] == "asked"
        )
    assert message["intervention"]["text"] == "It can be empty. What would make sense to return then?"
