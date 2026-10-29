"""The eval runner itself, offline: scripted models and runner, so it costs nothing and runs in CI."""

import json
from pathlib import Path
from typing import Any

import pytest

from crucible.coding.problems import ProblemBank
from crucible.contracts.events import CaseResult, RunResult, TimelineEvent, TimelineKind
from crucible.engine.codestate import BULK_INSERT_CHARS
from tests.evals.runner import (
    TYPE_CHUNK,
    RunReport,
    check,
    eval_passed,
    find_evals,
    load_eval,
    run_once,
    typing_changes,
    whole_change,
)
from tests.factories import QUIET_STREAK_REFERENCE, FakeModel, analysis, write_quiet_streak

QUIET = "def longest_quiet_streak(readings: list[int], threshold: int) -> int:\n"


# --- the eval file ------------------------------------------------------------------------------------------


def write_eval(tmp_path: Path, name: str, rows: list[dict[str, Any]]) -> Path:
    path = tmp_path / f"{name}.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def test_an_eval_loads_meta_steps_in_time_order_and_expectations(tmp_path: Path) -> None:
    path = write_eval(
        tmp_path,
        "demo",
        [
            {"meta": {"problem_slug": "quiet-streak"}},
            {"t": 9000, "do": "run"},
            {"t": 1000, "do": "say", "text": "hi"},
            {"expect": {"never": ["paste"]}},
        ],
    )
    spec = load_eval(path)
    assert (spec.name, [s.t for s in spec.steps], spec.expect) == ("demo", [1000, 9000], {"never": ["paste"]})


def test_an_eval_without_a_problem_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="problem_slug"):
        load_eval(write_eval(tmp_path, "bad", [{"meta": {}}]))


def test_the_shipped_evals_all_load_and_name_real_problems() -> None:
    bank = ProblemBank.load()
    evals = find_evals()
    assert len(evals) >= 6
    for spec in evals:
        assert bank.get(spec.meta["problem_slug"]) is not None, spec.name
        assert spec.expect, f"{spec.name} has no expectations"


# --- typing code ----------------------------------------------------------------------------------------------


def test_typed_code_comes_in_small_chunks_that_never_look_like_a_bulk_insert() -> None:
    old, new = QUIET + "    pass\n", QUIET + "    best = 0\n" * 20
    changes = typing_changes(old, new)
    assert changes[0].text == "" and changes[0].range_length > 0  # delete "pass" first
    assert all(len(c.text) <= TYPE_CHUNK < BULK_INSERT_CHARS for c in changes)
    code = old
    for c in changes:
        code = code[: c.range_offset] + c.text + code[c.range_offset + c.range_length :]
    assert code == new


def test_whole_change_finds_the_middle_that_differs() -> None:
    change = whole_change("abcXYZdef", "abcQdef")
    assert change is not None and (change.range_offset, change.range_length, change.text) == (3, 3, "Q")
    assert whole_change("same", "same") is None


# --- expectations ------------------------------------------------------------------------------------------------


def event(seq: int, t: int, kind: TimelineKind, payload: dict[str, Any]) -> TimelineEvent:
    return TimelineEvent(seq=seq, t=t, kind=kind, payload=payload)


def said(
    seq: int,
    t: int,
    trigger: str,
    step_id: str | None = None,
    text: str = "Think about it.",
    suppressed: bool = False,
) -> TimelineEvent:
    payload = {
        "id": f"i{seq}",
        "t": t,
        "trigger": trigger,
        "level": "nudge",
        "text": text,
        "step_id": step_id,
        "speak": False,
        "suppressed": suppressed,
    }
    return event(seq, t, TimelineKind.INTERVENTION, payload)


TIMELINE = [
    said(1, 0, "phase"),
    said(2, 20_000, "missed_step", "s1"),
    said(3, 30_000, "bug_suspected", text="best = max(best, cur) is the fix"),  # repeats the reference
    said(4, 40_000, "idle", suppressed=True),
    event(
        5,
        50_000,
        TimelineKind.INTEGRITY,
        {"id": "f1", "t": 50_000, "kind": "paste", "detail": "pasted", "chars": 50, "duration_ms": None},
    ),
    event(6, 10_000, TimelineKind.ANALYSIS, analysis("not_started", "in_progress", proposal=False)),
]


@pytest.mark.parametrize(
    ("expect", "oks"),
    [
        ({"fires": [{"trigger": "missed_step", "step_id": "s1", "by_t": 25_000}]}, [True]),
        ({"fires": [{"trigger": "missed_step", "by_t": 10_000}]}, [False]),  # too late
        ({"fires": [{"trigger": ["run_failed", "bug_suspected"]}]}, [True]),  # either trigger
        ({"never": ["idle", "silent"]}, [False, True]),  # decided counts, even suppressed
        ({"limits": [{"trigger": "missed_step", "max": 1}, {"trigger": "idle", "max": 0}]}, [True, False]),
        ({"max_shown": 1}, [False]),  # missed_step + bug_suspected shown; phase and suppressed don't count
        ({"max_shown": 2}, [True]),
        ({"no_leak": True}, [False]),
        ({"flags": ["paste"]}, [True]),
        ({"flags": ["tab_hidden"]}, [False]),
        ({"saw": [{"step_id": "s1", "status": "not_started", "by_t": 15_000}]}, [True]),
        ({"saw": [{"issue": "bug"}]}, [False]),
    ],
)
def test_each_expectation_is_checked(expect: dict[str, Any], oks: list[bool]) -> None:
    assert [ok for _, ok, _ in check(expect, TIMELINE, QUIET_STREAK_REFERENCE)] == oks


def test_an_eval_passes_on_two_of_three_runs() -> None:
    good, bad = RunReport(checks=[("x", True, "")]), RunReport(checks=[("x", False, "")])
    assert eval_passed([good, good, bad]) and not eval_passed([good, bad, bad])
    assert not eval_passed([good, RunReport(error="boom"), bad])


# --- a whole run, offline -----------------------------------------------------------------------------------------


class FakeRunner:
    """Answers every run with all tests passing."""

    async def open_session(self, session_id: str) -> None:
        return None

    async def close_session(self, session_id: str) -> None:
        return None

    async def run_tests(self, session_id: str, req: Any) -> RunResult:
        case = CaseResult(
            id="v1",
            visible=True,
            passed=True,
            input_repr="[]",
            expected_repr="0",
            actual_repr="0",
            error=None,
            runtime_ms=1,
        )
        return RunResult(
            run_id="r1",
            t=0,
            kind=req.kind,
            passed=1,
            total=1,
            cases=[case],
            stdout="",
            stderr="",
            timed_out=False,
            compile_error=None,
        )


@pytest.mark.asyncio
async def test_a_scripted_session_runs_through_the_real_engine(tmp_path: Path) -> None:
    write_quiet_streak(tmp_path)
    bank = ProblemBank.load(tmp_path)
    # The analyzer keeps seeing s1 (clarify) skipped while s2 is under way: MISSED_STEP should fire.
    model = FakeModel(analysis("not_started", "in_progress", proposal=False))
    path = write_eval(
        tmp_path,
        "skips",
        [
            {"meta": {"problem_slug": "quiet-streak", "voice": True}},
            {"t": 3000, "do": "say", "text": "I'll walk the readings once."},
            {
                "t": 8000,
                "do": "snapshot",
                "code": QUIET + "    best = cur = 0\n    for r in readings:\n        if r < threshold:\n",
            },
            {"t": 20000, "do": "say", "text": "Then I track the best run."},
            {"t": 30000, "do": "run"},
            {
                "expect": {
                    "fires": [{"trigger": "missed_step", "step_id": "s1", "by_t": 60000}],
                    "never": ["paste"],
                    "no_leak": True,
                }
            },
        ],
    )
    report = await run_once(load_eval(path), bank, model, lambda: FakeRunner())
    assert report.error is None, report.error
    assert report.passed, report.checks
    assert report.analyses >= 2
    assert any(i["trigger"] == "missed_step" for i in report.interventions)
