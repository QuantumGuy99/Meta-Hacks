"""Tests for engine/timeline.py (PLAN §9.2): numbering, validation, batching and the public replay view."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from crucible.contracts.defense import AuditResult
from crucible.contracts.events import (
    CaseResult,
    EditorEvent,
    Intervention,
    RunResult,
    SystemNote,
    TimelineEvent,
    TimelineKind,
)
from crucible.engine.store import MemoryStore
from crucible.engine.timeline import Timeline, TimelineError, public_view, redact_run

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def make_timeline(store: MemoryStore | None = None, last_seq: int = 0) -> tuple[Timeline, list[int]]:
    clock = [0]
    return Timeline("s1", store or MemoryStore(), lambda: clock[0], last_seq), clock


def note(message: str = "hi") -> SystemNote:
    return SystemNote(level="info", message=message)


def run(kind: str = "run", **case: object) -> RunResult:
    hidden = CaseResult(
        id="h1",
        visible=False,
        passed=False,
        input_repr="[1, 2, 3]",
        expected_repr="6",
        actual_repr="5",
        error="AssertionError: expected 6 for [1, 2, 3]",
        runtime_ms=1,
    )
    visible = hidden.model_copy(update={"id": "v1", "visible": True, **case})
    return RunResult(
        run_id="r1",
        t=10,
        kind=kind,
        passed=0,
        total=2,
        cases=[visible, hidden],
        stdout="[1, 2, 3]\n",
        stderr="",
        timed_out=False,
        compile_error=None,
    )


def test_append_numbers_events_and_stamps_the_clock() -> None:
    timeline, clock = make_timeline()
    clock[0] = 1500
    first = timeline.append(TimelineKind.SYSTEM, note())
    second = timeline.append(TimelineKind.SYSTEM, note(), t=42)
    assert (first.seq, first.t) == (1, 1500)
    assert (second.seq, second.t) == (2, 42)


def test_numbering_continues_from_last_seq() -> None:
    timeline, _ = make_timeline(last_seq=7)
    assert timeline.append(TimelineKind.SYSTEM, note()).seq == 8


def test_dict_payloads_are_validated_against_their_kind() -> None:
    timeline, _ = make_timeline()
    event = timeline.append(TimelineKind.SYSTEM, {"level": "warning", "message": "x"})
    assert event.payload == {"level": "warning", "message": "x"}
    with pytest.raises(ValidationError):
        timeline.append(TimelineKind.SYSTEM, {"level": "loud", "message": "x"})


def test_a_model_of_the_wrong_kind_is_rejected() -> None:
    timeline, _ = make_timeline()
    with pytest.raises(TimelineError):
        timeline.append(TimelineKind.EDITOR, note())


def test_tail_filters_by_kind() -> None:
    timeline, _ = make_timeline()
    timeline.append(TimelineKind.SYSTEM, note())
    timeline.append(TimelineKind.EDITOR, EditorEvent(t=1, version=2, kind="blur"))
    assert [e.kind for e in timeline.tail([TimelineKind.EDITOR])] == [TimelineKind.EDITOR]


@pytest.mark.asyncio
async def test_events_reach_the_store_only_on_flush() -> None:
    store = MemoryStore()
    timeline, _ = make_timeline(store)
    timeline.append(TimelineKind.SYSTEM, note("a"))
    assert await store.read_events("s1") == []
    await timeline.flush()
    assert [e.payload["message"] for e in await store.read_events("s1")] == ["a"]


@pytest.mark.asyncio
async def test_read_flushes_first_and_respects_since_seq() -> None:
    timeline, _ = make_timeline()
    for message in "abc":
        timeline.append(TimelineKind.SYSTEM, note(message))
    events = await timeline.read(since_seq=1)
    assert [e.payload["message"] for e in events] == ["b", "c"]


@pytest.mark.asyncio
async def test_a_failed_flush_keeps_the_events_for_the_next_one() -> None:
    class FlakyStore(MemoryStore):
        failures = 1

        async def append_events(self, session_id: str, events: list[TimelineEvent]) -> None:
            if self.failures:
                self.failures -= 1
                raise OSError("disk full")
            await super().append_events(session_id, events)

    store = FlakyStore()
    timeline, _ = make_timeline(store)
    timeline.append(TimelineKind.SYSTEM, note("a"))
    with pytest.raises(OSError):
        await timeline.flush()
    timeline.append(TimelineKind.SYSTEM, note("b"))
    await timeline.flush()
    assert [e.payload["message"] for e in await store.read_events("s1")] == ["a", "b"]


def test_hidden_cases_lose_their_details() -> None:
    redacted = redact_run(run())
    hidden = redacted.cases[1]
    assert (hidden.input_repr, hidden.expected_repr, hidden.actual_repr) == (None, None, None)
    assert hidden.error == "AssertionError"
    assert redacted.cases[0].input_repr == "[1, 2, 3]"  # visible cases are untouched
    assert redacted.stdout == "[1, 2, 3]\n"  # a Run only executes visible tests


def test_a_submit_drops_stdout_so_prints_cant_reveal_hidden_inputs() -> None:
    redacted = redact_run(run(kind="submit"))
    assert (redacted.stdout, redacted.stderr) == ("", "")


def _events() -> list[TimelineEvent]:
    timeline, _ = make_timeline()
    timeline.append(TimelineKind.RUN, run(kind="submit"))
    timeline.append(
        TimelineKind.ANALYSIS, json.loads((FIXTURES / "analysis.json").read_text(encoding="utf-8"))
    )
    timeline.append(TimelineKind.SYSTEM, note())
    shown = Intervention(
        id="i1",
        t=5,
        trigger="missed_step",
        level="nudge",
        text="Look at the end.",
        step_id="s2",
        speak=True,
        suppressed=False,
    )
    timeline.append(TimelineKind.INTERVENTION, shown)
    timeline.append(TimelineKind.INTERVENTION, shown.model_copy(update={"id": "i2", "suppressed": True}))
    timeline.append(
        TimelineKind.AUDIT,
        AuditResult.model_validate_json((FIXTURES / "audit_result.json").read_text(encoding="utf-8")),
    )
    return timeline.tail()


def test_live_view_hides_hints_and_answers() -> None:
    shown = public_view(_events(), live=True)
    kinds = [e.kind for e in shown]
    assert TimelineKind.ANALYSIS not in kinds and TimelineKind.SYSTEM not in kinds
    assert [e.payload["id"] for e in shown if e.kind == TimelineKind.INTERVENTION] == ["i1"]
    audit = next(e for e in shown if e.kind == TimelineKind.AUDIT)
    assert "explanation" not in audit.payload["findings"][0]
    assert "grill" not in audit.payload["findings"][0]


def test_finished_view_shows_everything_but_hidden_tests() -> None:
    shown = public_view(_events(), live=False)
    assert len(shown) == 6
    audit = next(e for e in shown if e.kind == TimelineKind.AUDIT)
    assert "explanation" in audit.payload["findings"][0]
    run_event = next(e for e in shown if e.kind == TimelineKind.RUN)
    assert run_event.payload["cases"][1]["input_repr"] is None
