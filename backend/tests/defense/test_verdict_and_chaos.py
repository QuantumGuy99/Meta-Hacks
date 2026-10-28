"""Merge gate and chaos verdict are pure functions (PLAN §11.4, §11.6)."""

from crucible.contracts.defense import ChaosRun, GrillEval, GrillTurn
from crucible.defense.chaos import ChaosDone, decide_verdict, parse_line
from crucible.defense.verdict import decide


def done(ok=True, requests=1000, errors=0, p95=50.0, detail="all good") -> ChaosDone:
    return ChaosDone(
        invariant_ok=ok,
        violations=0 if ok else 12,
        detail=detail,
        requests=requests,
        errors=errors,
        p95_ms=p95,
        p99_ms=p95,
    )


def test_chaos_verdicts():
    assert decide_verdict(done(), None) == ("held", [])
    assert decide_verdict(done(ok=False, detail="$70 disappeared"), None) == ("broke", ["$70 disappeared"])
    assert decide_verdict(done(errors=60), None)[0] == "broke"  # 6% > 5%
    assert decide_verdict(done(errors=50), None)[0] == "held"  # exactly 5% is allowed
    assert decide_verdict(done(p95=900), 500)[0] == "broke"
    assert decide_verdict(done(p95=900), None)[0] == "held"
    assert decide_verdict(None, None)[0] == "error"
    assert decide_verdict(done(requests=0), None)[0] == "error"


def test_parse_line_handles_metrics_done_and_noise():
    m = parse_line(
        '{"t_ms": 500, "in_flight": 3, "rps": 10, "p50_ms": 1, "p95_ms": 2, "p99_ms": 3, '
        '"errors": 0, "violations": 4}',
        "r1",
    )
    assert m.run_id == "r1" and m.violations == 4
    d = parse_line(
        '{"done": true, "invariant_ok": false, "violations": 4, "detail": "x", "requests": 9}', "r1"
    )
    assert isinstance(d, ChaosDone) and not d.invariant_ok
    assert parse_line("Traceback (most recent call last):", "r1") is None
    assert parse_line('{"t_ms": "oops"}', "r1") is None
    assert parse_line("[1, 2]", "r1") is None


def run(verdict: str) -> ChaosRun:
    return ChaosRun(
        id="r",
        finding_id="f1",
        kind="verify",
        attempt=1,
        script="",
        verdict=verdict,
        summary=verdict,
        detail="",
        metrics=[],
    )


def turn(score: int, root: bool) -> GrillTurn:
    return GrillTurn(
        finding_id="f1",
        question="q",
        answer_turn_ids=["a"],
        follow_up_asked=False,
        eval=GrillEval(points_hit=[], points_missed=[], needs_follow_up=False, feedback=""),
        sam_node_id=None,
        root_cause_hit=root,
        score=score,
    )


def test_gate_passes_only_with_hold_score_and_root_cause():
    assert decide(["f1"], {"f1": run("held")}, {"f1": turn(7, True)}).passed
    assert not decide(["f1"], {"f1": run("broke")}, {"f1": turn(10, True)}).passed
    assert not decide(["f1"], {"f1": run("held")}, {"f1": turn(5, True)}).passed
    assert not decide(["f1"], {"f1": run("held")}, {"f1": turn(8, False)}).passed
    assert not decide(["f1"], {}, {"f1": turn(10, True)}).passed
    assert not decide([], {}, {}).passed  # nothing broke → nothing proven → no pass
