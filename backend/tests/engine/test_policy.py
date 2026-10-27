"""Tests for engine/policy.py, ENG-4's thin version (MISSED_STEP only). ENG-5 adds the full rule table."""

from crucible.contracts.coding import Analysis, ProblemSpec
from crucible.contracts.events import InterventionLevel, InterventionTrigger
from crucible.engine.policy import COOLDOWN_MS, QUIET_AFTER_EDIT_MS, PolicyState, decide, missed_steps
from tests.factories import analysis, problem_json

STEPS = ProblemSpec.model_validate(problem_json()).rubric.steps
NOW = 100_000


def run_twice(first: dict, second: dict, state: PolicyState | None = None, **kwargs: object):
    state = state or PolicyState()
    state.previous = Analysis.model_validate(first)
    return decide(
        Analysis.model_validate(second), state, steps=STEPS, now_ms=NOW, last_edit_ms=None, **kwargs
    )


def test_a_skipped_step_behind_work_in_progress_is_missed() -> None:
    assert missed_steps(Analysis.model_validate(analysis()), STEPS) == {"s1"}


def test_a_later_step_attempted_wrongly_still_counts_as_under_way() -> None:
    # Seen live: Spark at minimal effort marks a buggy loop "incorrect" rather than "in_progress".
    assert missed_steps(Analysis.model_validate(analysis(s2="incorrect")), STEPS) == {"s1"}


def test_nothing_is_missed_before_any_later_step_starts() -> None:
    assert missed_steps(Analysis.model_validate(analysis(s2="not_started")), STEPS) == set()


def test_fires_when_the_same_step_is_missed_in_two_analyses() -> None:
    decision = run_twice(analysis(), analysis())
    assert decision is not None
    assert (decision.trigger, decision.level, decision.step_id) == (
        InterventionTrigger.MISSED_STEP,
        InterventionLevel.NUDGE,
        "s1",
    )
    assert decision.draft == "Before you go further, what should an empty list give you?"


def test_does_not_fire_on_the_first_analysis() -> None:
    assert (
        decide(Analysis.model_validate(analysis()), PolicyState(), steps=STEPS, now_ms=NOW, last_edit_ms=None)
        is None
    )


def test_does_not_fire_when_the_step_was_done_last_time() -> None:
    assert run_twice(analysis(s1="done"), analysis()) is None


def test_waits_out_the_cooldown() -> None:
    state = PolicyState(last_unsolicited_ms=NOW - COOLDOWN_MS + 1)
    assert run_twice(analysis(), analysis(), state) is None


def test_never_interrupts_right_after_an_edit() -> None:
    state = PolicyState(previous=Analysis.model_validate(analysis()))
    current = Analysis.model_validate(analysis())
    assert decide(current, state, steps=STEPS, now_ms=NOW, last_edit_ms=NOW - QUIET_AFTER_EDIT_MS + 1) is None


def test_never_repeats_the_same_nudge() -> None:
    state = PolicyState()
    decision = run_twice(analysis(), analysis(), state)
    assert decision is not None
    state.remember(decision, NOW - COOLDOWN_MS * 2)
    assert run_twice(analysis(), analysis(), state) is None


def test_holds_when_the_analyzer_is_unsure() -> None:
    assert run_twice(analysis(), analysis(confidence=0.5)) is None


def test_uses_the_rubric_hint_when_the_draft_is_at_another_level() -> None:
    decision = run_twice(analysis(), analysis(level="hint"))
    assert decision is not None and decision.draft is None
