"""Tests for engine/interviewer.py: the code check, the fallback text and delivery (PLAN §9.6)."""

from dataclasses import replace

import pytest

from crucible.contracts.coding import ProblemSpec
from crucible.contracts.events import InterventionLevel, InterventionTrigger, TimelineKind
from crucible.engine.context import RubricContext
from crucible.engine.interviewer import deliver, fallback_text, looks_like_code, rubric_hint
from crucible.engine.policy import Decision
from crucible.engine.prompts import CANNED
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


POLICY_TRIGGERS = [
    InterventionTrigger.ASKED,
    InterventionTrigger.HINT_REQUESTED,
    InterventionTrigger.TIME_WARNING,
    InterventionTrigger.PASTE,
    InterventionTrigger.CODED_BEFORE_PLAN,
    InterventionTrigger.RUN_FAILED,
    InterventionTrigger.BUG_SUSPECTED,
    InterventionTrigger.PLAN_MISMATCH,
    InterventionTrigger.SILENT,
    InterventionTrigger.IDLE,
]


@pytest.mark.parametrize("key", [t.value for t in POLICY_TRIGGERS] + ["concept"])
def test_every_policy_trigger_has_a_canned_line_without_code(key: str) -> None:
    assert CANNED[key] and not looks_like_code(CANNED[key])


def fallback(
    trigger: InterventionTrigger, level: InterventionLevel, step_id: str | None, **extra: object
) -> str:
    return fallback_text(CONTEXT, Decision(trigger, level, step_id, None, **extra), remaining_s=301)


def test_ladder_rules_fall_back_to_the_rubric_hint() -> None:
    hint = fallback(InterventionTrigger.RUN_FAILED, InterventionLevel.QUESTION, "s2")
    assert hint == CONTEXT.steps[1].hints[1]


def test_the_concept_level_has_its_own_line() -> None:
    assert fallback(InterventionTrigger.MISSED_STEP, InterventionLevel.CONCEPT, "s1") == CANNED["concept"]


def test_other_rules_fall_back_to_their_canned_line() -> None:
    assert (
        fallback(InterventionTrigger.HINT_REQUESTED, InterventionLevel.NUDGE, None)
        == CANNED["hint_requested"]
    )
    assert fallback(InterventionTrigger.BUG_SUSPECTED, InterventionLevel.NUDGE, None, line=7) == CANNED[
        "bug_suspected"
    ].format(line=7)
    time_left = fallback(InterventionTrigger.TIME_WARNING, InterventionLevel.INFO, None)
    assert time_left == CANNED["time_warning"].format(minutes=6)


@pytest.mark.asyncio
async def test_a_rubric_hint_with_code_in_it_is_replaced_by_a_generic_line() -> None:
    step = CONTEXT.steps[0].model_copy(update={"hints": ["if not readings:\n    return 0", "?", "?"]})
    leaky = replace(CONTEXT, steps=[step, *CONTEXT.steps[1:]])
    intervention = await deliver(runtime(), NUDGE, leaky)
    assert intervention.text == rubric_hint(CONTEXT, "nope", InterventionLevel.NUDGE)


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", [InterventionTrigger.PASTE, InterventionTrigger.TIME_WARNING])
async def test_paste_and_time_notes_are_shown_but_not_spoken(trigger: InterventionTrigger) -> None:
    intervention = await deliver(runtime(), Decision(trigger, InterventionLevel.INFO, None, None), CONTEXT)
    assert not intervention.speak and not intervention.suppressed


@pytest.mark.asyncio
async def test_a_suppressed_decision_is_logged_but_not_shown() -> None:
    rt = runtime()
    intervention = await deliver(rt, replace(NUDGE, suppressed=True), CONTEXT)
    assert intervention.suppressed
    assert [e.kind for e in rt.timeline.tail()] == [TimelineKind.INTERVENTION]


@pytest.mark.asyncio
async def test_passive_mode_still_shows_answers() -> None:
    answer = Decision(InterventionTrigger.ASKED, InterventionLevel.QUESTION, None, None)
    intervention = await deliver(runtime(feedback="passive"), answer, CONTEXT)
    assert not intervention.suppressed and intervention.text == CANNED["asked"]
