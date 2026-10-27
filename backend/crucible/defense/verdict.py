"""Merge gate: a pure function of verify runs and grill turns (PLAN §11.6)."""

from __future__ import annotations

from crucible.contracts.defense import ChaosRun, GrillTurn, Verdict

PASS_AVG_GRILL = 6.0


def decide(
    grilled: list[str],
    verify_runs: dict[str, ChaosRun],
    grill_turns: dict[str, GrillTurn],
    baseline_runs: dict[str, ChaosRun] | None = None,
) -> Verdict:
    """passed = every grilled finding's verify held AND avg grill ≥ 6 AND every root cause was named."""
    reasons: list[str] = []
    fixed, unfixed = [], []
    if not grilled:
        reasons.append("no finding broke under load, so nothing was proven or defended")
    for fid in grilled:
        run = verify_runs.get(fid)
        if run is not None and run.verdict == "held":
            fixed.append(fid)
            before = (baseline_runs or {}).get(fid)
            if before is not None:
                reasons.append(
                    f"{fid}: held under the same attack (violations "
                    f"{_last_violations(before)} → {_last_violations(run)})"
                )
        else:
            unfixed.append(fid)
            reasons.append(f"{fid}: {'not verified yet' if run is None else run.summary}")
        turn = grill_turns.get(fid)
        if turn is None:
            reasons.append(f"{fid}: not grilled")
        elif not turn.root_cause_hit:
            reasons.append(f"{fid}: the explanation didn't name the root cause")
    scores = [grill_turns[f].score for f in grilled if f in grill_turns]
    avg = round(sum(scores) / len(scores), 1) if scores else 0.0
    if avg < PASS_AVG_GRILL:
        reasons.append(f"average grill score {avg} (needs {PASS_AVG_GRILL:.0f})")
    passed = (
        bool(grilled)
        and not unfixed
        and avg >= PASS_AVG_GRILL
        and all(f in grill_turns and grill_turns[f].root_cause_hit for f in grilled)
    )
    return Verdict(
        passed=passed, reasons=reasons, findings_fixed=fixed, findings_unfixed=unfixed, avg_grill_score=avg
    )


def _last_violations(run: ChaosRun) -> int:
    return run.metrics[-1].violations if run.metrics else 0
