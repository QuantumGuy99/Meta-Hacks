"""Tests for engine/interviewer.py, ENG-4's thin version: the code check and delivery."""

import pytest

from crucible.contracts.coding import ProblemSpec
from crucible.contracts.events import InterventionLevel, InterventionTrigger, TimelineKind
from crucible.engine.context import RubricContext
from crucible.engine.interviewer import deliver, looks_like_code, rubric_hint
from crucible.engine.policy import Decision
from tests.factories import problem_json, runtime

CONTEXT = RubricContext.from_problem(ProblemSpec.model_validate(problem_json()))
NUDGE = Decision(InterventionTrigger.MISSED_STEP, InterventionLevel.NUDGE, "s1", None)


@pytest.mark.parametrize(
    "text",
    [
        "Try this:\n```python\nbest = max(best, cur)\n```",
        "best = max(best, cur)\nreturn best",
        "if not readings:\n    return 0",
    ],
)
def test_code_is_caught(text: str) -> None:
    assert looks_like_code(text)


@pytest.mark.parametrize(
    "text",
    [
        "What should an empty list give you?",
        "Look at what happens on your last reading.",
        "Think about the case where every reading is quiet.\nWhat would your loop return?",
        "total",
    ],
)
def test_prose_is_not_code(text: str) -> None:
    assert not looks_like_code(text)


def test_rubric_hints_follow_the_ladder() -> None:
    assert rubric_hint(CONTEXT, "s1", InterventionLevel.NUDGE).startswith("Before you code")
    assert (
        rubric_hint(CONTEXT, "s1", InterventionLevel.QUESTION)
        == "What should happen if there are no readings at all?"
    )
    assert "walk me through" in rubric_hint(CONTEXT, "nope", InterventionLevel.NUDGE)


@pytest.mark.asyncio
async def test_delivery_records_and_logs_what_the_interviewer_said() -> None:
    rt = runtime()
    intervention = await deliver(rt, NUDGE, CONTEXT)
    assert intervention.text == rubric_hint(CONTEXT, "s1", InterventionLevel.NUDGE)
    assert not intervention.suppressed
    kinds = [e.kind for e in rt.timeline.tail()]
    assert kinds == [TimelineKind.INTERVENTION, TimelineKind.TRANSCRIPT]


@pytest.mark.asyncio
async def test_a_draft_with_code_is_replaced_by_the_rubric_hint() -> None:
    rt = runtime()
    leaky = Decision(
        InterventionTrigger.MISSED_STEP, InterventionLevel.NUDGE, "s1", "if not xs:\n    return 0"
    )
    intervention = await deliver(rt, leaky, CONTEXT)
    assert intervention.text == rubric_hint(CONTEXT, "s1", InterventionLevel.NUDGE)
    assert any(e.kind == TimelineKind.SYSTEM for e in rt.timeline.tail())


@pytest.mark.asyncio
async def test_passive_mode_records_but_does_not_show() -> None:
    rt = runtime(feedback="passive")
    intervention = await deliver(rt, NUDGE, CONTEXT)
    assert intervention.suppressed
    assert [e.kind for e in rt.timeline.tail()] == [TimelineKind.INTERVENTION]
