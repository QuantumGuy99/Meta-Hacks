"""Chaos lab: run a rendered attack against the project in the Runner, stream metrics, decide the verdict
in code (PLAN §11.4)."""

from __future__ import annotations

import json
import logging
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError

from crucible.contracts.defense import AttackFunctions, ChaosMetric, ChaosRun, Finding, Project
from crucible.contracts.events import TimelineKind
from crucible.defense.attack_writer import clamp_load, render_attack
from crucible.defense.ports import EventSink, note
from crucible.runner.base import Runner, RunnerError

logger = logging.getLogger(__name__)

ERROR_PCT_LIMIT = 5.0
EXEC_SLACK_S = 30  # on top of the attack's duration; PLAN §21 caps a chaos run at 60 s


@dataclass(slots=True)
class ChaosDone:
    invariant_ok: bool
    violations: int
    detail: str
    requests: int
    errors: int
    p95_ms: float
    p99_ms: float


def parse_line(line: str, run_id: str) -> ChaosMetric | ChaosDone | None:
    """One stdout line → a metric, the final summary, or None (not ours: logs, tracebacks)."""
    try:
        raw = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    try:
        if raw.get("done"):
            return ChaosDone(
                invariant_ok=bool(raw["invariant_ok"]),
                violations=int(raw.get("violations", 0)),
                detail=str(raw["detail"]),
                requests=int(raw.get("requests", 0)),
                errors=int(raw.get("errors", 0)),
                p95_ms=float(raw.get("p95_ms", 0)),
                p99_ms=float(raw.get("p99_ms", 0)),
            )
        return ChaosMetric.model_validate({**raw, "run_id": run_id})
    except (KeyError, TypeError, ValueError, ValidationError):
        logger.warning("bad chaos line: %.200s", line)
        return None


def decide_verdict(
    done: ChaosDone | None, p95_threshold_ms: int | None
) -> tuple[Literal["broke", "held", "error"], list[str]]:
    """broke if the invariant failed, errors > 5% or p95 > a positive threshold; held otherwise; error if
    no result."""
    if done is None:
        return "error", ["the attack ended without a result"]
    if done.requests == 0:
        return "error", ["the attack sent no requests"]
    reasons = []
    if not done.invariant_ok:
        reasons.append(done.detail)
    err_pct = 100 * done.errors / done.requests
    if err_pct > ERROR_PCT_LIMIT:
        reasons.append(f"{err_pct:.1f}% of requests failed (limit {ERROR_PCT_LIMIT:.0f}%)")
    if p95_threshold_ms and done.p95_ms > p95_threshold_ms:  # 0 or None: no latency check (#43)
        reasons.append(f"p95 {done.p95_ms:.0f} ms (limit {p95_threshold_ms} ms)")
    return ("broke" if reasons else "held"), reasons


async def run_attack(
    runner: Runner,
    project: Project,
    files: dict[str, str],
    finding: Finding,
    functions: AttackFunctions,
    sink: EventSink,
    *,
    kind: Literal["baseline", "verify"],
    attempt: int = 1,
    duration_override_s: int | None = None,
) -> ChaosRun:
    if finding.chaos is None:
        raise ValueError(f"finding {finding.id} has no chaos plan")
    concurrency, duration_s = clamp_load(
        finding.chaos.concurrency, duration_override_s or finding.chaos.duration_s, category=finding.category
    )
    run_id = uuid.uuid4().hex[:12]
    metrics: list[ChaosMetric] = []
    done: ChaosDone | None = None
    tail: deque[str] = deque(maxlen=15)
    script = ""
    failure = ""
    try:
        h = await runner.start_project(project, files)
    except RunnerError as exc:
        failure = f"the app didn't start: {exc}"
    else:
        try:
            script = render_attack(functions, port=h.port, concurrency=concurrency, duration_s=duration_s)
            await runner.put_file(h, "attack.py", script)
            async for line in runner.stream_exec(
                h, ["python", "attack.py"], timeout_s=duration_s + EXEC_SLACK_S
            ):
                item = parse_line(line, run_id)
                if isinstance(item, ChaosMetric):
                    metrics.append(item)
                    await sink.emit(TimelineKind.CHAOS_METRIC, item)
                elif isinstance(item, ChaosDone):
                    done = item
                elif line.strip():
                    tail.append(line)
        except RunnerError as exc:
            failure = str(exc)
        finally:
            await runner.stop_project(h)

    verdict, reasons = decide_verdict(done, finding.chaos.p95_threshold_ms)
    if failure:
        verdict, reasons = "error", [failure]
    detail = "\n".join(
        reasons + ([f"output tail:\n{chr(10).join(tail)}"] if verdict == "error" and tail else [])
    )
    run = ChaosRun(
        id=run_id,
        finding_id=finding.id,
        kind=kind,
        attempt=attempt,
        script=script,
        verdict=verdict,
        summary=_summary(verdict, done, concurrency, reasons),
        detail=detail,
        metrics=metrics,
    )
    if verdict == "error":
        await note(sink, "error", f"Chaos {kind} for {finding.id} errored: {reasons[0]}")
    await sink.emit(TimelineKind.CHAOS_RUN, run)
    return run


def _summary(verdict: str, done: ChaosDone | None, concurrency: int, reasons: list[str]) -> str:
    if done is None or verdict == "error":
        return f"Couldn't run the attack: {reasons[0]}"
    err_pct = 100 * done.errors / max(done.requests, 1)
    numbers = (
        f"{done.requests:,} requests at {concurrency} concurrent, p95 {done.p95_ms:.0f} ms, "
        f"{err_pct:.1f}% errors"
    )
    head = reasons[0] if verdict == "broke" else "Held: the invariant stayed intact"
    return f"{head} ({numbers})"
