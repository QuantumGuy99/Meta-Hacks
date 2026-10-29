"""Tests for engine/policy.py: each rule fires and holds back, each guard works (PLAN §9.5)."""

from collections import deque
from typing import Any

import pytest

from crucible.contracts.coding import Analysis, ProblemSpec
from crucible.contracts.common import Phase
from crucible.contracts.events import (
    CaseResult,
    EditorChange,
    EditorEvent,
    InterventionLevel,
    InterventionTrigger,
    RunResult,
)
from crucible.engine.policy import (
    BUG_STABLE_MS,
    CAP_COUNT,
    CAP_WINDOW_MS,
    COOLDOWN_MS,
    HOLD_MAX_MS,
    IDLE_AFTER_MS,
    IDLE_EVERY_MS,
    QUIET_AFTER_EDIT_MS,
    RUN_IDLE_MS,
    SILENT_AFTER_MS,
    SILENT_EVERY_MS,
    Decision,
    Facts,
    PolicyState,
    decide,
    is_question,
    missed_steps,
    written_lines,
)
from tests.factories import analysis, problem_json

Trigger, Level = InterventionTrigger, InterventionLevel
STEPS = ProblemSpec.model_validate(problem_json()).rubric.steps
NOW = 100_000
CODE = """\
def longest_quiet_streak(readings, threshold):
    best = cur = 0
    for r in readings:
        cur = cur + 1 if r <= threshold else 0
    return best
"""
CLEAN = analysis(s1="done", proposal=False)  # nothing for the analysis rules to say
ISSUE = {
    "kind": "bug",
    "line": 4,
    "description": "counts loud readings",
    "mistake_id": None,
    "confidence": 0.9,
}


def facts(now: int = NOW, **changes: Any) -> Facts:
    """A quiet moment in `coding`: the candidate typed and spoke 10 s ago."""
    values: dict[str, Any] = {
        "now_ms": now,
        "phase": Phase.CODING,
        "phase_started_ms": 0,
        "passive": False,
        "voice": True,
        "time_limit_s": 3600,
        "steps": STEPS,
        "code": CODE,
        "lines_written": 0,
        "last_edit_ms": now - 10_000,
        "last_speech_ms": now - 10_000,
        "last_partial_ms": None,
    }
    return Facts(**(values | changes))


def seen(*analyses: dict[str, Any], state: PolicyState | None = None) -> PolicyState:
    state = state or PolicyState()
    for item in analyses:
        state.observe_analysis(Analysis.model_validate(item))
    return state


def what(decision: Decision | None) -> tuple[InterventionTrigger, InterventionLevel, str | None] | None:
    return None if decision is None else (decision.trigger, decision.level, decision.step_id)


def paste(text: str, kind: str = "paste") -> EditorEvent:
    return EditorEvent(
        t=0, version=1, kind=kind, changes=[EditorChange(range_offset=0, range_length=0, text=text)]
    )


def run(t: int, *failing: str) -> RunResult:
    cases = [
        CaseResult(
            id=case_id,
            visible=case_id.startswith("v"),
            passed=case_id not in failing,
            input_repr=None,
            expected_repr=None,
            actual_repr=None,
            error=None,
            runtime_ms=1,
        )
        for case_id in ("v1", "v2", "h1")
    ]
    passed = sum(c.passed for c in cases)
    return RunResult(
        run_id=f"r{t}",
        t=t,
        kind="run",
        passed=passed,
        total=len(cases),
        cases=cases,
        stdout="",
        stderr="",
        timed_out=False,
        compile_error=None,
    )


# --- helpers ---------------------------------------------------------------------------------------------------


def test_a_skipped_step_behind_work_in_progress_is_missed() -> None:
    assert missed_steps(Analysis.model_validate(analysis()), STEPS) == {"s1"}


def test_a_later_step_attempted_wrongly_still_counts_as_under_way() -> None:
    # Seen live: Spark at minimal effort marks a buggy loop "incorrect" rather than "in_progress".
    assert missed_steps(Analysis.model_validate(analysis(s2="incorrect")), STEPS) == {"s1"}


def test_nothing_is_missed_before_any_later_step_starts() -> None:
    assert missed_steps(Analysis.model_validate(analysis(s2="not_started")), STEPS) == set()


@pytest.mark.parametrize("text", ["Can the list be empty?", "is equal to the threshold quiet", "hello?"])
def test_questions_are_recognised(text: str) -> None:
    assert is_question(text)


@pytest.mark.parametrize("text", ["I'll loop over the readings.", "Then I'll track the best run.", "  "])
def test_thinking_aloud_in_chat_is_not_a_question(text: str) -> None:
    assert not is_question(text)


def test_the_starter_code_does_not_count_as_written() -> None:
    starter = "def f(xs):\n    pass\n"
    assert written_lines(starter, starter) == 0
    assert written_lines(starter, "def f(xs):\n    total = 0\n\n    for x in xs:\n        total += x\n") == 3


# --- ASKED -----------------------------------------------------------------------------------------------------


def test_asked_answers_at_once_even_mid_typing_and_in_cooldown() -> None:
    state = PolicyState(last_message_ms=NOW - 1_000)
    state.ask()
    decision = decide(state, facts(last_edit_ms=NOW - 100))
    assert what(decision) == (Trigger.ASKED, Level.QUESTION, None)


def test_asked_does_not_fire_without_a_question() -> None:
    assert decide(seen(CLEAN, CLEAN), facts()) is None


# --- HINT_REQUESTED --------------------------------------------------------------------------------------------


def test_a_hint_request_gets_a_nudge_for_the_first_required_step_not_done() -> None:
    state = PolicyState()
    state.request_hint(None)
    assert what(decide(state, facts())) == (Trigger.HINT_REQUESTED, Level.NUDGE, "s1")


def test_a_hint_request_for_a_named_step_is_about_that_step() -> None:
    state = PolicyState()
    state.request_hint("s2")
    assert what(decide(state, facts())) == (Trigger.HINT_REQUESTED, Level.NUDGE, "s2")


def test_a_hint_request_follows_the_analyzers_step_and_wording() -> None:
    state = seen(analysis(s1="done"))
    state.request_hint(None)
    decision = decide(state, facts())
    assert decision is not None and decision.step_id == "s1"
    assert decision.draft == "Before you go further, what should an empty list give you?"


def test_no_hint_without_a_request() -> None:
    assert decide(PolicyState(), facts()) is None


def test_the_ladder_climbs_to_concept_and_counts_every_level() -> None:
    state = PolicyState()
    levels = []
    for i in range(5):
        state.request_hint("s1")
        decision = decide(state, facts(NOW + i))
        assert decision is not None
        levels.append(decision.level)
    assert levels == [Level.NUDGE, Level.QUESTION, Level.HINT, Level.CONCEPT, Level.CONCEPT]
    assert state.hints_by_level == {"nudge": 1, "question": 1, "hint": 1, "concept": 2}


# --- TIME_WARNING ----------------------------------------------------------------------------------------------


def test_time_warnings_fire_at_half_and_four_fifths_once_each() -> None:
    state = PolicyState()
    assert decide(state, facts(499_999, time_limit_s=1000)) is None
    assert what(decide(state, facts(500_000, time_limit_s=1000))) == (Trigger.TIME_WARNING, Level.INFO, None)
    assert decide(state, facts(500_001, time_limit_s=1000)) is None
    assert what(decide(state, facts(800_000, time_limit_s=1000))) == (Trigger.TIME_WARNING, Level.INFO, None)
    assert decide(state, facts(900_000, time_limit_s=1000)) is None


def test_passing_both_marks_at_once_gives_one_warning() -> None:
    state = PolicyState()
    assert decide(state, facts(850_000, time_limit_s=1000)) is not None
    assert decide(state, facts(850_001, time_limit_s=1000)) is None


def test_time_warnings_ignore_the_cooldown() -> None:
    state = PolicyState(last_message_ms=499_000)
    assert decide(state, facts(500_000, time_limit_s=1000)) is not None


# --- PASTE -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "event",
    [
        paste("x" * 40),
        paste("a = 1\nb = 2"),
        paste("y" * 80, kind="change"),  # a bulk insert without a paste event
    ],
)
def test_a_paste_or_bulk_insert_gets_a_note(event: EditorEvent) -> None:
    state = PolicyState()
    state.observe_edit(event)
    assert what(decide(state, facts())) == (Trigger.PASTE, Level.INFO, None)


@pytest.mark.parametrize("event", [paste("x" * 39), paste("a\n\n"), paste("y" * 79, kind="change")])
def test_small_pastes_and_typing_get_no_note(event: EditorEvent) -> None:
    state = PolicyState()
    state.observe_edit(event)
    assert decide(state, facts()) is None


def test_the_paste_note_is_said_once() -> None:
    state = PolicyState()
    state.observe_edit(paste("x" * 50))
    assert decide(state, facts()) is not None
    state.observe_edit(paste("z" * 50))
    assert decide(state, facts(NOW + COOLDOWN_MS)) is None


# --- CODED_BEFORE_PLAN -----------------------------------------------------------------------------------------

NO_PLAN = CLEAN | {"stated_plan": None, "plan_matches_code": None}


def test_three_lines_without_a_plan_get_asked_for_the_approach() -> None:
    decision = decide(seen(NO_PLAN), facts(lines_written=3))
    assert what(decision) == (Trigger.CODED_BEFORE_PLAN, Level.QUESTION, None)


@pytest.mark.parametrize(
    ("state_analysis", "changes"),
    [
        (CLEAN, {"lines_written": 3}),  # the plan was stated
        (NO_PLAN, {"lines_written": 2}),
        (NO_PLAN, {"lines_written": 3, "voice": False}),
    ],
)
def test_no_approach_question_with_a_plan_few_lines_or_voice_off(
    state_analysis: dict[str, Any], changes: dict[str, Any]
) -> None:
    assert decide(seen(state_analysis), facts(**changes)) is None


def test_a_plan_stated_earlier_still_counts_after_it_leaves_the_analyzers_window() -> None:
    # COD-6: the analyzer sees 90 s of transcript; a plan stated before that must not trigger the question.
    assert decide(seen(CLEAN, NO_PLAN), facts(lines_written=5)) is None


def test_the_policy_remembers_the_latest_stated_plan() -> None:
    state = seen(CLEAN, NO_PLAN, NO_PLAN)
    assert state.plan == CLEAN["stated_plan"]


# --- RUN_FAILED ------------------------------------------------------------------------------------------------


def test_the_same_visible_test_failing_twice_starts_the_ladder() -> None:
    state = PolicyState()
    state.observe_run(run(NOW - 20_000, "v1"))
    state.observe_run(run(NOW - 5_000, "v1"))
    assert what(decide(state, facts())) == (Trigger.RUN_FAILED, Level.NUDGE, "s1")


def test_one_failure_then_thirty_quiet_seconds_starts_the_ladder() -> None:
    state = PolicyState()
    state.observe_run(run(NOW - RUN_IDLE_MS, "v1"))
    quiet = facts(last_edit_ms=NOW - RUN_IDLE_MS - 1, last_speech_ms=NOW - RUN_IDLE_MS - 1)
    assert what(decide(state, quiet)) == (Trigger.RUN_FAILED, Level.NUDGE, "s1")


def test_one_failure_while_the_candidate_keeps_working_is_left_alone() -> None:
    state = PolicyState()
    state.observe_run(run(NOW - RUN_IDLE_MS, "v1"))
    assert decide(state, facts()) is None


def test_different_tests_failing_or_hidden_failures_are_left_alone() -> None:
    state = PolicyState()
    state.observe_run(run(NOW - 20_000, "v1", "h1"))
    state.observe_run(run(NOW - 5_000, "v2", "h1"))
    assert decide(state, facts()) is None


def test_a_failing_test_points_at_the_step_marked_incorrect() -> None:
    state = seen(analysis(s1="done", s2="incorrect", proposal=False))
    state.observe_run(run(NOW - 20_000, "v1"))
    state.observe_run(run(NOW - 5_000, "v1"))
    assert what(decide(state, facts())) == (Trigger.RUN_FAILED, Level.NUDGE, "s2")


# --- MISSED_STEP -----------------------------------------------------------------------------------------------


def test_a_step_missed_in_two_analyses_gets_a_nudge_in_the_analyzers_words() -> None:
    decision = decide(seen(analysis(), analysis()), facts())
    assert what(decision) == (Trigger.MISSED_STEP, Level.NUDGE, "s1")
    assert (
        decision is not None
        and decision.draft == "Before you go further, what should an empty list give you?"
    )


def test_a_missed_step_waits_for_a_second_analysis() -> None:
    assert decide(seen(analysis()), facts()) is None


def test_a_step_done_last_time_is_not_missed() -> None:
    assert decide(seen(analysis(s1="done"), analysis()), facts()) is None


def test_a_missed_step_waits_while_the_analyzer_is_unsure() -> None:
    assert decide(seen(analysis(), analysis(confidence=0.5)), facts()) is None


def test_a_draft_at_another_level_falls_back_to_the_rubric() -> None:
    decision = decide(seen(analysis(), analysis(level="hint")), facts())
    assert decision is not None and decision.draft is None


def test_a_missed_step_climbs_the_ladder_only_on_fresh_analyses() -> None:
    state = seen(analysis(), analysis())
    assert decide(state, facts()) is not None
    later = NOW + COOLDOWN_MS
    assert decide(state, facts(later)) is None  # same two analyses: no new evidence
    seen(analysis(), analysis(), state=state)
    assert what(decide(state, facts(later))) == (Trigger.MISSED_STEP, Level.QUESTION, "s1")


# --- BUG_SUSPECTED ---------------------------------------------------------------------------------------------

BUGGY = CLEAN | {"issues": [ISSUE]}


def test_a_likely_bug_on_a_line_left_alone_for_20_s_gets_pointed_at() -> None:
    state = seen(BUGGY, BUGGY)
    assert decide(state, facts()) is None  # the line has to sit still first
    decision = decide(state, facts(NOW + BUG_STABLE_MS))
    assert what(decision) == (Trigger.BUG_SUSPECTED, Level.NUDGE, None)
    assert decision is not None and decision.line == 4 and decision.draft is None


def test_a_likely_bug_is_not_pointed_at_while_its_line_changes() -> None:
    state = seen(BUGGY, BUGGY)
    decide(state, facts())
    edited = CODE.replace("r <= threshold", "r < threshold")
    assert decide(state, facts(NOW + BUG_STABLE_MS, code=edited)) is None


@pytest.mark.parametrize(
    "pair",
    [
        (CLEAN, BUGGY),  # seen once
        (CLEAN | {"issues": [ISSUE | {"confidence": 0.7}]},) * 2,
        (CLEAN | {"issues": [ISSUE | {"kind": "style"}]},) * 2,
    ],
)
def test_a_bug_seen_once_unsure_or_cosmetic_is_left_alone(pair: tuple[dict[str, Any], ...]) -> None:
    state = seen(*pair)
    decide(state, facts())
    assert decide(state, facts(NOW + BUG_STABLE_MS)) is None


def test_each_bug_is_pointed_at_once() -> None:
    state = seen(BUGGY, BUGGY)
    decide(state, facts())
    assert decide(state, facts(NOW + BUG_STABLE_MS)) is not None
    seen(BUGGY, BUGGY, state=state)
    assert decide(state, facts(NOW + BUG_STABLE_MS + COOLDOWN_MS)) is None


# --- PLAN_MISMATCH ---------------------------------------------------------------------------------------------

MISMATCH = CLEAN | {"plan_matches_code": False}


def test_code_off_plan_in_two_analyses_gets_a_question() -> None:
    assert what(decide(seen(MISMATCH, MISMATCH), facts())) == (Trigger.PLAN_MISMATCH, Level.QUESTION, None)


def test_code_off_plan_once_is_left_alone() -> None:
    assert decide(seen(CLEAN, MISMATCH), facts()) is None


def test_code_off_an_earlier_plan_still_gets_a_question() -> None:
    # The latest analyses no longer quote the plan, but still judge the code against the one shown to them.
    drifted = MISMATCH | {"stated_plan": None}
    decision = decide(seen(CLEAN, drifted, drifted), facts())
    assert what(decision) == (Trigger.PLAN_MISMATCH, Level.QUESTION, None)


def test_no_plan_ever_means_no_mismatch() -> None:
    never = NO_PLAN | {"plan_matches_code": False}
    assert decide(seen(never, never), facts(lines_written=1)) is None


# --- SILENT ----------------------------------------------------------------------------------------------------


def silent(now: int = NOW + SILENT_AFTER_MS, **changes: Any) -> Facts:
    return facts(now, last_speech_ms=NOW, **changes)


def test_two_silent_minutes_of_coding_get_a_nudge_to_talk() -> None:
    assert what(decide(PolicyState(), silent())) == (Trigger.SILENT, Level.NUDGE, None)


@pytest.mark.parametrize("changes", [{"voice": False}, {"phase": Phase.CLARIFY}])
def test_no_talk_nudge_with_voice_off_or_outside_coding(changes: dict[str, Any]) -> None:
    assert decide(PolicyState(), silent(**changes)) is None


def test_the_talk_nudge_repeats_at_most_every_five_minutes() -> None:
    state = PolicyState()
    first = NOW + SILENT_AFTER_MS
    assert decide(state, silent(first)) is not None
    assert decide(state, silent(first + SILENT_EVERY_MS - 1)) is None
    assert decide(state, silent(first + SILENT_EVERY_MS)) is not None


# --- IDLE ------------------------------------------------------------------------------------------------------


def idle(now: int = NOW + IDLE_AFTER_MS, **changes: Any) -> Facts:
    # Voice off, so SILENT (two quiet minutes) stays out of the way.
    return facts(now, **({"last_edit_ms": NOW, "last_speech_ms": NOW, "voice": False} | changes))


def test_75_s_without_edits_or_speech_gets_a_check_in() -> None:
    assert what(decide(PolicyState(), idle())) == (Trigger.IDLE, Level.QUESTION, None)


@pytest.mark.parametrize(
    "changes", [{"last_edit_ms": NOW + 1}, {"last_speech_ms": NOW + 1}, {"phase": Phase.WRAP_UP}]
)
def test_no_check_in_after_recent_work_or_outside_coding(changes: dict[str, Any]) -> None:
    assert decide(PolicyState(), idle(**changes)) is None


def test_the_check_in_repeats_at_most_every_three_minutes() -> None:
    state = PolicyState()
    first = NOW + IDLE_AFTER_MS
    assert decide(state, idle(first)) is not None
    assert decide(state, idle(first + IDLE_EVERY_MS - 1)) is None
    assert decide(state, idle(first + IDLE_EVERY_MS)) is not None


# --- order and global guards -----------------------------------------------------------------------------------


def test_the_first_matching_rule_wins() -> None:
    state = seen(analysis(), analysis())
    state.observe_edit(paste("x" * 50))
    assert what(decide(state, facts())) == (Trigger.PASTE, Level.INFO, None)
    assert decide(state, facts(NOW + 1)) is None  # the cooldown now holds the missed step back


def test_unsolicited_messages_are_45_s_apart() -> None:
    state = seen(analysis(), analysis(), state=PolicyState(last_message_ms=NOW - COOLDOWN_MS + 1))
    assert decide(state, facts()) is None
    assert decide(state, facts(NOW + 1)) is not None


def test_an_answer_restarts_the_cooldown() -> None:
    state = seen(analysis(), analysis())
    state.ask()
    assert what(decide(state, facts())) == (Trigger.ASKED, Level.QUESTION, None)
    assert decide(state, facts(NOW + 1_000)) is None


def test_at_most_eight_unsolicited_messages_per_30_min() -> None:
    times = deque(NOW - CAP_WINDOW_MS + 60_000 * (i + 1) for i in range(CAP_COUNT))
    state = seen(analysis(), analysis(), state=PolicyState(unsolicited_ms=times))
    assert decide(state, facts()) is None
    assert decide(state, facts(NOW + 60_000)) is not None  # the oldest one left the window


def test_the_same_message_is_never_logged_twice() -> None:
    # Passive mode doesn't climb the ladder, so the same (trigger, step, level) comes up again.
    state = seen(analysis(), analysis())
    assert decide(state, facts(passive=True)) is not None
    seen(analysis(), analysis(), state=state)
    assert decide(state, facts(NOW + COOLDOWN_MS, passive=True)) is None


def test_a_message_waits_for_typing_to_pause_then_goes_out() -> None:
    state = seen(analysis(), analysis())
    assert decide(state, facts(last_edit_ms=NOW - 1_000)) is None
    assert state.held is not None
    later = NOW - 1_000 + QUIET_AFTER_EDIT_MS
    assert what(decide(state, facts(later, last_edit_ms=NOW - 1_000))) == (
        Trigger.MISSED_STEP,
        Level.NUDGE,
        "s1",
    )


def test_a_message_waits_while_the_candidate_is_talking() -> None:
    state = seen(analysis(), analysis())
    assert decide(state, facts(last_partial_ms=NOW - 500)) is None
    assert decide(state, facts(NOW + 2_000, last_partial_ms=NOW - 500)) is not None


def test_a_message_held_for_more_than_20_s_is_dropped_until_new_evidence() -> None:
    state = seen(analysis(), analysis())
    assert decide(state, facts(last_edit_ms=NOW - 100)) is None
    stale = NOW + HOLD_MAX_MS + 1
    assert decide(state, facts(stale, last_edit_ms=stale - 100)) is None
    assert state.held is None
    assert decide(state, facts(stale + 10_000)) is None  # quiet now, but the evidence is old
    seen(analysis(), analysis(), state=state)
    assert what(decide(state, facts(stale + 10_000))) == (Trigger.MISSED_STEP, Level.NUDGE, "s1")


# --- passive mode ----------------------------------------------------------------------------------------------


def test_passive_mode_logs_unsolicited_messages_as_suppressed() -> None:
    state = seen(analysis(), analysis())
    decision = decide(state, facts(passive=True))
    assert decision is not None and decision.suppressed
    assert state.ladder == {} and state.hints_by_level == {}  # the candidate saw nothing


def test_passive_mode_still_answers_hints_and_tells_the_time() -> None:
    state = PolicyState()
    state.ask()
    state.request_hint(None)
    shown = [decide(state, facts(500_000 + i, passive=True, time_limit_s=1000)) for i in range(3)]
    assert [(d.trigger, d.suppressed) for d in shown if d is not None] == [
        (Trigger.ASKED, False),
        (Trigger.HINT_REQUESTED, False),
        (Trigger.TIME_WARNING, False),
    ]
    assert state.hints_by_level == {"nudge": 1}
