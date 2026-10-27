"""The whole Defense pipeline, standalone, on the local runner with every model down (pure fallbacks):
the original code breaks, the reference fix holds, the gate follows the explanation (PLAN §3.2)."""

import pytest

from crucible.contracts.common import Phase
from crucible.defense import audit as audit_mod
from crucible.defense.pipeline import DefensePipeline, run_scripted
from crucible.runner.local import LocalRunner
from tests.defense.fixtures import GOOD_ANSWER, WEAK_ANSWER

pytestmark = pytest.mark.e2e
DURATION = 3


@pytest.fixture(autouse=True)
def _clear_cache():
    audit_mod._CACHE.clear()


def pipeline(bank, local_settings, llm_down, sink) -> DefensePipeline:
    return DefensePipeline(bank, LocalRunner(local_settings), llm_down, sink, duration_override_s=DURATION)


async def test_break_explain_fix_verify_pass(bank, local_settings, llm_down, sink):
    p = pipeline(bank, local_settings, llm_down, sink)
    verdict = await run_scripted(p, GOOD_ANSWER, bank.fixed_files)

    base = p.state.baseline["f1"]
    assert base.verdict == "broke", base.detail
    assert "disappeared" in base.summary or "appeared from nowhere" in base.summary
    assert len(base.metrics) >= DURATION  # live metrics every 0.5 s
    assert any(m.violations > 0 for m in base.metrics)
    assert p.state.verify["f1"].verdict == "held", p.state.verify["f1"].detail
    assert p.state.grill["f1"].root_cause_hit
    assert verdict.passed, verdict.reasons
    assert p.state.phase == Phase.VERDICT
    kinds = sink.kinds()
    for k in ("phase", "audit", "chaos_metric", "chaos_run", "grill", "verdict"):
        assert k in kinds
    audit_event = next(e for e in sink.public_events() if e["kind"] == "audit")
    assert "explanation" not in str(audit_event)  # what the browser sees


async def test_weak_explanation_fails_the_gate_even_when_fixed(bank, local_settings, llm_down, sink):
    p = pipeline(bank, local_settings, llm_down, sink)
    verdict = await run_scripted(p, WEAK_ANSWER, bank.fixed_files)
    assert p.state.verify["f1"].verdict == "held"
    assert not verdict.passed
    assert any("root cause" in r for r in verdict.reasons)


async def test_unfixed_code_fails_verify_and_returns_to_fix(bank, local_settings, llm_down, sink):
    p = pipeline(bank, local_settings, llm_down, sink)
    await p.run_audit()
    await p.run_baselines()
    await p.answer_grill("f1", GOOD_ANSWER)
    run = await p.verify("f1", {})
    assert run.verdict == "broke"
    assert p.state.phase == Phase.FIX


async def test_follow_up_adds_points_and_only_once(bank, local_settings, llm_down, sink):
    p = pipeline(bank, local_settings, llm_down, sink)
    await p.run_audit()
    await p.run_baselines()
    first = await p.answer_grill("f1", WEAK_ANSWER)
    assert not first.root_cause_hit and p.needs_follow_up("f1")
    second = await p.answer_grill("f1", GOOD_ANSWER)
    assert second.root_cause_hit and second.follow_up_asked and len(second.answer_turn_ids) == 2
    assert not p.needs_follow_up("f1")
    with pytest.raises(LookupError):
        await p.answer_grill("f1", GOOD_ANSWER)


async def test_verify_rejects_unknown_files(bank, local_settings, llm_down, sink):
    p = pipeline(bank, local_settings, llm_down, sink)
    await p.run_audit()
    await p.run_baselines()
    with pytest.raises(ValueError):
        await p.verify("f1", {"app/new_file.py": "x = 1"})
