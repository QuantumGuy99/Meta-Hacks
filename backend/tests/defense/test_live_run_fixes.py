"""Fixes from the live runs with real models (#35, #43): the backup attack, grading, latency, load, audits."""

import asyncio
from types import SimpleNamespace

import pytest

from crucible.contracts.common import Phase
from crucible.contracts.defense import AuditResult
from crucible.contracts.events import PhaseChange, TimelineEvent, TimelineKind
from crucible.defense import audit as audit_mod
from crucible.defense.attack_writer import RACE_MIN_CONCURRENCY, clamp_load
from crucible.defense.audit import audit_from_flaws, derive_topology, run_audit
from crucible.defense.chaos import ChaosDone, decide_verdict
from crucible.defense.controller import DefenseController
from crucible.defense.grill import keyword_eval
from crucible.defense.pipeline import reference_target
from tests.defense.fixtures import WEAK_ANSWER, FakeLLM

# What a live Wonder audit wrote for bank-transfer: long compound points (#43 point 1).
COMPOUND_POINTS = [
    "ledger.transfer reads the source and destination balances into locals, awaits the external fraud scoring "
    "call, then writes balances computed from those stale locals, so concurrent transfers on a shared account "
    "lose updates and the conservation of money invariant breaks.",
    "During the await other coroutines interleave and write the same accounts; it also accepts transfers that "
    "should fail for insufficient funds and can create or destroy money when a source or destination is shared.",
    "Serialize the read-check-write per account with an asyncio.Lock acquired in a consistent order, or move to "
    "a single atomic SQL UPDATE inside a transaction.",
]
CORRECT = (
    "The transfer reads the sender's balance, then awaits the fraud check, then writes balance minus amount. "
    "Two concurrent transfers read the same old balance, so the second write overwrites the first and money "
    "disappears. I'd hold a per-account lock around the read and the write, or do it in one database transaction."
)


def _model_finding(bank, **update):
    """A finding as a live audit names it: its own id, slightly different lines."""
    return audit_from_flaws(bank).findings[0].model_copy(update={"id": "balance-race", **update})


def test_reference_attack_matches_a_model_finding_by_file_and_lines(bank):
    found = _model_finding(bank, line_start=38, line_end=48)
    assert reference_target([found], bank.flaws, "f1") == "balance-race"


def test_reference_attack_falls_back_to_the_first_chaos_finding(bank):
    elsewhere = _model_finding(bank, file="app/other.py")
    assert reference_target([elsewhere], bank.flaws, "f1") == "balance-race"


def test_no_chaos_finding_means_no_reference_target(bank):
    assert reference_target([_model_finding(bank, chaos=None)], bank.flaws, "f1") is None


def test_keyword_fallback_credits_a_correct_root_cause_on_compound_points():
    assert 0 in keyword_eval(COMPOUND_POINTS, CORRECT).points_hit


def test_keyword_fallback_still_misses_a_weak_answer():
    assert keyword_eval(COMPOUND_POINTS, WEAK_ANSWER).points_hit == []
    assert keyword_eval(COMPOUND_POINTS, "No idea, honestly.").points_hit == []


def _done(p95_ms: float) -> ChaosDone:
    return ChaosDone(
        invariant_ok=True,
        violations=0,
        detail="all accounted for",
        requests=1000,
        errors=0,
        p95_ms=p95_ms,
        p99_ms=p95_ms,
    )


@pytest.mark.parametrize("limit", [0, None])
def test_a_zero_or_missing_latency_limit_means_no_latency_check(limit):
    assert decide_verdict(_done(p95_ms=30), limit)[0] == "held"


def test_a_positive_latency_limit_still_breaks():
    assert decide_verdict(_done(p95_ms=300), 100)[0] == "broke"


def test_race_findings_get_a_concurrency_floor():
    assert clamp_load(20, 5, category="race_condition") == (RACE_MIN_CONCURRENCY, 5)
    assert clamp_load(20, 5, category="blocking_io") == (20, 5)


@pytest.fixture(autouse=True)
def _no_audit_cache(monkeypatch):
    monkeypatch.setattr(audit_mod, "_CACHE", {})


async def test_an_empty_audit_is_retried_once(bank, sink):
    llm = FakeLLM()
    empty = AuditResult(summary="", nodes=[], edges=[], findings=[])
    llm.push("audit", empty)
    llm.push("audit", audit_from_flaws(bank))
    result = await run_audit(bank, llm, sink)
    assert llm.calls == ["audit", "audit"] and result.findings


async def test_two_empty_audits_fall_back_to_flaws_json(bank, sink):
    llm = FakeLLM()
    empty = AuditResult(summary="", nodes=[], edges=[], findings=[])
    llm.push("audit", empty)
    llm.push("audit", empty)
    result = await run_audit(bank, llm, sink)
    assert [f.id for f in result.findings] == ["f1"]


async def test_session_end_cancels_running_defense_stages():
    controller = DefenseController(mode=None)
    long_stage = asyncio.create_task(asyncio.sleep(60))  # an attack still running
    controller._tasks.add(long_stage)
    ended = PhaseChange(from_phase=Phase.CHAOS, to_phase=Phase.ENDED, reason="ended by the candidate")
    event = TimelineEvent(seq=9, t=1000, kind=TimelineKind.PHASE, payload=ended.model_dump(mode="json"))
    await controller.on_timeline(SimpleNamespace(), event)
    assert long_stage.cancelled()


def test_fallback_topology_sees_package_style_imports():
    files = {"app/main.py": "from app import ledger, store\n", "app/ledger.py": "x = 1\n", "app/store.py": ""}
    _, edges = derive_topology(files)
    assert {(e.source, e.target) for e in edges} == {("app.main", "app.ledger"), ("app.main", "app.store")}
