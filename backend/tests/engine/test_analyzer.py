"""Tests for engine/analyzer.py (PLAN §9.4): when the analyzer runs, what it sees, and failed calls."""

import pytest

from crucible.contracts.coding import Analysis, ProblemSpec
from crucible.contracts.events import CaseResult, RunResult, TimelineKind, TranscriptTurn
from crucible.engine.analyzer import (
    MIN_GAP_MS,
    PAUSE_MS,
    STEADY_CHANGE_MS,
    AnalysisInput,
    SchedulerState,
    build_messages,
    due,
)
from crucible.engine.context import RubricContext
from tests.factories import QUIET_STREAK_REFERENCE, FakeModel, analysis, problem_json, runtime


def context() -> RubricContext:
    spec = ProblemSpec.model_validate(
        {
            **problem_json(),
            "statement_md": "Count quiet readings.",
            "reference_solution": QUIET_STREAK_REFERENCE,
        }
    )
    return RubricContext.from_problem(spec)


# --- due() -----------------------------------------------------------------------------------------------


def test_nothing_is_due_without_changes_or_triggers() -> None:
    assert due(SchedulerState(), now_ms=60_000, code_changed=False) is None


def test_a_typing_pause_triggers_after_2_5_s() -> None:
    state = SchedulerState(last_edit_ms=10_000, first_change_ms=10_000)
    assert due(state, 10_000 + PAUSE_MS - 1, code_changed=True) is None
    assert due(state, 10_000 + PAUSE_MS, code_changed=True) == "pause"


def test_a_pause_needs_a_real_change() -> None:
    state = SchedulerState(last_edit_ms=10_000, first_change_ms=10_000)
    assert due(state, 20_000, code_changed=False) is None


def test_the_8_s_floor_holds_back_runs_and_pauses() -> None:
    state = SchedulerState(last_edit_ms=0, first_change_ms=0, last_started_ms=5_000, pending={"run"})
    assert due(state, 5_000 + MIN_GAP_MS - 1, code_changed=True) is None
    assert due(state, 5_000 + MIN_GAP_MS, code_changed=True) == "run"


def test_an_ask_skips_the_floor() -> None:
    state = SchedulerState(last_started_ms=5_000, pending={"ask"})
    assert due(state, 5_001, code_changed=False) == "ask"


def test_a_spoken_turn_is_a_trigger() -> None:
    assert due(SchedulerState(pending={"turn"}), 1_000, code_changed=False) == "turn"


def test_steady_typing_is_looked_at_every_30_s() -> None:
    state = SchedulerState(last_edit_ms=STEADY_CHANGE_MS, first_change_ms=0)
    assert due(state, STEADY_CHANGE_MS, code_changed=True) == "steady_change"


# --- build_messages() ----------------------------------------------------------------------------------------


def view(**overrides: object) -> AnalysisInput:
    hidden = CaseResult(
        id="h1",
        visible=False,
        passed=False,
        input_repr="[7, 7, 7], 9",
        expected_repr="3",
        actual_repr="0",
        error="WrongAnswer",
        runtime_ms=1,
    )
    run = RunResult(
        run_id="r1",
        t=60_000,
        kind="submit",
        passed=0,
        total=1,
        cases=[hidden],
        stdout="",
        stderr="",
        timed_out=False,
        compile_error=None,
    )
    turn = TranscriptTurn(
        turn_id="t1",
        speaker="candidate",
        text="I'll keep a running count",
        start_ms=50_000,
        end_ms=52_000,
        final=True,
        source="voice",
    )
    values = {
        "phase": "coding",
        "elapsed_s": 75,
        "remaining_s": 1125,
        "feedback": "active",
        "files": {"solution.py": "def f(xs):\n    best = 0\n"},
        "diffs": {"solution.py": "+    best = 0\n"},
        "runs": [run],
        "transcript": [turn],
        "previous": None,
        "interventions": [],
    }
    return AnalysisInput(**{**values, **overrides})


def test_messages_put_the_static_problem_before_the_live_state() -> None:
    system, problem, state = build_messages(context(), view())
    assert system["role"] == "system" and "Never write solution code" in system["content"]
    assert "Quiet Streak" in problem["content"] and "def longest_quiet_streak(" in problem["content"]
    assert "Clarify the input" in problem["content"]
    assert state["content"].startswith("# Now")


def test_code_is_numbered_and_speech_is_included() -> None:
    state = build_messages(context(), view())[2]["content"]
    assert "  2 |     best = 0" in state
    assert "I'll keep a running count" in state


def test_hidden_test_inputs_and_the_reference_never_reach_the_prompt() -> None:
    text = "\n".join(m["content"] for m in build_messages(context(), view()))
    assert "[7, 7, 7]" not in text and "hidden tests: 0/1 passed" in text
    assert "best = max(best, cur)" not in text


def test_previous_statuses_and_given_interventions_are_listed() -> None:
    previous = Analysis.model_validate(analysis())
    state = build_messages(context(), view(previous=previous))[2]["content"]
    assert "- s1: not_started" in state


# --- Analyzer.run ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_successful_run_records_the_analysis() -> None:
    model = FakeModel(analysis())
    rt = runtime(model)
    await rt.attach(context())
    try:
        result = await rt._engine.analyzer.run("ask")  # type: ignore[union-attr]
    finally:
        await rt.detach()
    assert result is not None
    assert [e.kind for e in rt.timeline.tail()] == [TimelineKind.ANALYSIS]
    assert model.calls[0][0]["role"] == "system"


@pytest.mark.asyncio
async def test_a_failed_call_skips_the_tick_and_keeps_the_changes_for_next_time() -> None:
    rt = runtime(FakeModel(RuntimeError("model down")))
    await rt.attach(context())
    rt.code.code_by_file["solution.py"] = "x = 1\n"
    try:
        result = await rt._engine.analyzer.run("pause")  # type: ignore[union-attr]
    finally:
        await rt.detach()
    assert result is None
    notes = rt.timeline.tail([TimelineKind.SYSTEM])
    assert len(notes) == 1 and "analysis skipped" in notes[0].payload["message"]
    assert rt.code.changed_since_analysis()
