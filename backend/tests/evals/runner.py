"""The coding eval runner (PLAN §13.3, §18): scripted candidate sessions through the real engine.

An eval (JSONL, format in plan/sharvil-data.md) records what the candidate did; the engine produces the rest. The
runner drives the session hub in-process on a simulated clock. Between steps it advances time in 0.5 s ticks, runs
the analyzer whenever `due()` says so and ticks the policy, as the live loops do. Code steps are typed as edits a
line at a time, so the session moves to `coding` the way it does in the room. An eval passes when every
expectation holds in at least 2 of its runs (3 by default). Results go to `tests/evals/results/<date>.md`.

    uv run python -m tests.evals.runner                        # every eval, 3 runs each (costs credits)
    uv run python -m tests.evals.runner --only off-by-one --runs 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from crucible.coding.problems import ProblemBank
from crucible.coding.session import CodingMode
from crucible.config import Settings
from crucible.contracts.coding import ProblemSpec
from crucible.contracts.common import Mode, SessionConfig
from crucible.contracts.events import (
    CodeSnapshot,
    EditorChange,
    EditorEvent,
    TimelineEvent,
    TimelineKind,
    TranscriptTurn,
)
from crucible.contracts.ws import (
    ChatSend,
    ClientMessage,
    CodeRun,
    CodeSubmit,
    EditorEvents,
    EditorSnapshot,
    HintRequest,
    PhaseAdvance,
)
from crucible.engine.analyzer import StructuredModel, due
from crucible.engine.hub import Connection, SessionHub, SessionRuntime
from crucible.engine.ids import new_id
from crucible.engine.interviewer import leak_reason
from crucible.engine.store import MemoryStore
from crucible.runner.base import Runner

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
EVAL_DIRS = (REPO / "data" / "evals" / "coding", HERE / "cases")  # Sharvil's evals, then ours
PROBLEMS = REPO / "data" / "problems"
RESULTS = HERE / "results"
TICK_MS = 500  # the policy loop's tick (§9.5)
TAIL_MS = 30_000  # time after the last step for pending nudges to land
TYPE_CHUNK = 60  # characters per simulated keystroke batch; under the bulk-insert flag's 80
RUNS = 3
PASS_RUNS = 2
NOT_UNSOLICITED = frozenset({"phase", "asked", "hint_requested", "grill"})
SPEAKING_MS_PER_CHAR = 60


# --- the eval file ----------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Step:
    t: int
    do: str
    text: str | None = None
    code: str | None = None
    pasted: str | None = None
    to: str | None = None


@dataclass(frozen=True, slots=True)
class Eval:
    name: str
    meta: dict[str, Any]
    steps: tuple[Step, ...]
    expect: dict[str, Any]


def load_eval(path: Path) -> Eval:
    meta: dict[str, Any] = {}
    expect: dict[str, Any] = {}
    steps: list[Step] = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if "meta" in row:
            meta = row["meta"]
        elif "expect" in row:
            expect = row["expect"]
        elif "do" in row:
            steps.append(Step(**row))
        else:
            raise ValueError(f"{path.name}:{number}: a line needs meta, expect or do")
    if "problem_slug" not in meta:
        raise ValueError(f"{path.name}: meta.problem_slug is required")
    return Eval(path.stem, meta, tuple(sorted(steps, key=lambda s: s.t)), expect)


def find_evals(dirs: Iterable[Path] = EVAL_DIRS, only: str | None = None) -> list[Eval]:
    paths = sorted(p for d in dirs if d.is_dir() for p in d.glob("*.jsonl"))
    return [load_eval(p) for p in paths if only is None or only in p.stem]


# --- driving one session -------------------------------------------------------------------------------------------


class SimClock:
    """The session's clocks, moved by the runner instead of by time passing."""

    BASE = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)

    def __init__(self) -> None:
        self.s = 0.0

    def monotonic(self) -> float:
        return 1_000.0 + self.s

    def wall(self) -> datetime:
        return self.BASE + timedelta(seconds=self.s)


class Tab:
    """The candidate's browser tab: keeps what the server sent."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_text(self, data: str) -> None:
        self.messages.append(json.loads(data))


@dataclass(slots=True)
class Play:
    """One run of one eval."""

    rt: SessionRuntime
    connection: Connection
    clock: SimClock
    tab: Tab
    file: str = "solution.py"
    code: str = ""
    version: int = 1

    def now_ms(self) -> int:
        return self.rt.now_ms()

    async def advance_to(self, t_ms: int) -> None:
        """Move the clock to `t_ms` in policy ticks, running the analyzer when it's due."""
        while self.now_ms() < t_ms:
            self.clock.s = min(t_ms, self.now_ms() + TICK_MS) / 1000
            await self.tick()

    async def tick(self) -> None:
        engine = self.rt._engine
        if engine is None:  # detached: wrap-up or the session ended
            return
        reason = due(engine.analyzer.state, self.now_ms(), self.rt.code.changed_since_analysis())
        if reason is not None:
            await engine.analyzer.run(reason)
        await engine.tick()
        await asyncio.sleep(0)

    async def send(self, msg: ClientMessage) -> None:
        await self.rt.handle(self.connection, msg)
        await asyncio.sleep(0)

    async def apply(self, step: Step) -> None:
        match step.do:
            case "snapshot":
                await self.type_code(step.code or "")
            case "paste":
                await self.paste(step.code or "", step.pasted)
            case "say":
                await self.say(step.text or "")
                await self.classified()
            case "chat":
                await self.send(ChatSend(type="chat.send", text=step.text or ""))
            case "run":
                await self.run("run")
            case "submit":
                await self.run("submit")
            case "hint":
                await self.send(HintRequest(type="hint.request"))
            case "advance":
                await self.send(PhaseAdvance(type="phase.advance", to=step.to))  # type: ignore[arg-type]
            case "end":
                pass  # the runner stops here; it never builds a report (that's ENG-8's own check)
            case other:
                raise ValueError(f"unknown step: {other}")

    async def type_code(self, target: str) -> None:
        """Turn the code into the edits a candidate would type, then reconcile with a snapshot."""
        events = [self.edit("change", change) for change in typing_changes(self.code, target)]
        if events:
            await self.send(EditorEvents(type="editor.events", events=events))
        await self.snapshot()

    async def paste(self, target: str, pasted: str | None) -> None:
        change = whole_change(self.code, target)
        if change is not None:
            event = self.edit("paste", change, pasted_chars=len(pasted) if pasted else len(change.text))
            await self.send(EditorEvents(type="editor.events", events=[event]))
        await self.snapshot()

    def edit(self, kind: str, change: EditorChange, pasted_chars: int | None = None) -> EditorEvent:
        start, end = change.range_offset, change.range_offset + change.range_length
        self.code = self.code[:start] + change.text + self.code[end:]
        self.version += 1
        return EditorEvent(
            t=self.now_ms(),
            file=self.file,
            version=self.version,
            kind=kind,  # type: ignore[arg-type]
            changes=[change],
            pasted_chars=pasted_chars,
        )

    async def snapshot(self) -> None:
        snapshot = CodeSnapshot(t=self.now_ms(), file=self.file, version=self.version, code=self.code)
        await self.send(EditorSnapshot(type="editor.snapshot", snapshot=snapshot))

    async def say(self, text: str) -> None:
        now = self.now_ms()
        turn = TranscriptTurn(
            turn_id=new_id(),
            speaker="candidate",
            text=text,
            start_ms=max(0, now - len(text) * SPEAKING_MS_PER_CHAR),
            end_ms=now,
            final=True,
            source="voice",
        )
        await self.rt.record(TimelineKind.TRANSCRIPT, turn)

    async def classified(self) -> None:
        """Let the voice classifier (COD-6) finish on what was just said, as it would while the candidate pauses."""
        engine = self.rt._engine
        if engine is not None:
            await settle(lambda: not engine._classifying)

    async def run(self, kind: str) -> None:
        msg_type = CodeRun if kind == "run" else CodeSubmit
        await self.send(msg_type(type=f"code.{kind}", file=self.file, code=self.code))  # type: ignore[arg-type]
        await settle(lambda: len(self.rt.timeline.tail([TimelineKind.RUN])) > 0 and not self.run_pending())

    def run_pending(self) -> bool:
        runs = self.rt.timeline.tail([TimelineKind.RUN])
        sent = sum(1 for m in self.tab.messages if m["type"] == "run.result")
        return sent < len(runs)


async def settle(done: Callable[[], bool], timeout_s: float = 30) -> None:
    """Wait (in real time) for work the hub runs in its own tasks, such as a test run."""
    async with asyncio.timeout(timeout_s):
        while not done():  # noqa: ASYNC110  # the hub's tasks don't signal; the runner polls
            await asyncio.sleep(0.02)


def typing_changes(old: str, new: str) -> list[EditorChange]:
    """The edits that turn `old` into `new`: delete what changed, then type the rest in small chunks."""
    change = whole_change(old, new)
    if change is None:
        return []
    changes = []
    if change.range_length:
        changes.append(
            EditorChange(range_offset=change.range_offset, range_length=change.range_length, text="")
        )
    offset = change.range_offset
    for start in range(0, len(change.text), TYPE_CHUNK):
        chunk = change.text[start : start + TYPE_CHUNK]
        changes.append(EditorChange(range_offset=offset, range_length=0, text=chunk))
        offset += len(chunk)
    return changes


def whole_change(old: str, new: str) -> EditorChange | None:
    """One change replacing the middle that differs (after the common prefix, before the common suffix)."""
    if old == new:
        return None
    prefix = 0
    while prefix < min(len(old), len(new)) and old[prefix] == new[prefix]:
        prefix += 1
    suffix = 0
    while suffix < min(len(old), len(new)) - prefix and old[-1 - suffix] == new[-1 - suffix]:
        suffix += 1
    return EditorChange(
        range_offset=prefix, range_length=len(old) - prefix - suffix, text=new[prefix : len(new) - suffix]
    )


# --- one run ---------------------------------------------------------------------------------------------------------


@dataclass(slots=True)
class RunReport:
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    interventions: list[dict[str, Any]] = field(default_factory=list)
    analyses: int = 0
    seconds: float = 0.0
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and all(ok for _, ok, _ in self.checks)


async def run_once(
    spec: Eval, bank: ProblemBank, model: StructuredModel, runner: Callable[[], Runner]
) -> RunReport:
    started = time.monotonic()
    clock, tab = SimClock(), Tab()
    hub = SessionHub(
        MemoryStore(),
        {Mode.CODING: CodingMode(bank, runner=runner)},
        model=model,
        monotonic=clock.monotonic,
        wall=clock.wall,
    )
    report = RunReport()
    problem = bank.get(spec.meta["problem_slug"])
    try:
        if problem is None:
            raise ValueError(f"no problem {spec.meta['problem_slug']!r} in {PROBLEMS}")
        play = await open_play(hub, spec, clock, tab, problem)
        for step in spec.steps:
            await play.advance_to(step.t)
            await play.apply(step)
            if step.do == "end":
                break
        await play.advance_to(play.now_ms() + TAIL_MS)
        events = await play.rt.timeline.read()
        report.checks = check(spec.expect, events, problem.reference_solution)
        report.interventions = [e.payload | {"t": e.t} for e in events if e.kind == TimelineKind.INTERVENTION]
        report.analyses = sum(e.kind == TimelineKind.ANALYSIS for e in events)
    except Exception as exc:  # one broken run is reported, not raised, so the other runs still count
        logger.exception("eval %s failed to run", spec.name)
        report.error = f"{type(exc).__name__}: {exc}"
    finally:
        await hub.close()
    report.seconds = time.monotonic() - started
    return report


async def open_play(hub: SessionHub, spec: Eval, clock: SimClock, tab: Tab, problem: ProblemSpec) -> Play:
    meta = spec.meta
    config = SessionConfig(
        mode=Mode.CODING,
        problem_slug=meta["problem_slug"],
        feedback=meta.get("feedback", "active"),
        voice=meta.get("voice", True),
        speak_replies=False,
    )
    session = await hub.create_session(config)
    rt, connection = await hub.connect(session.id, tab)
    await settle(lambda: rt._engine is not None)  # the intro, then clarify attaches the engine
    await rt._engine.stop()  # type: ignore[union-attr]  # from here the runner drives it on the simulated clock
    play = Play(rt, connection, clock, tab, code=problem.starter_code)
    await play.snapshot()  # the editor loads the starter code
    return play


# --- expectations ----------------------------------------------------------------------------------------------------


def check(
    expect: dict[str, Any], events: Sequence[TimelineEvent], reference: str | None
) -> list[tuple[str, bool, str]]:
    """Each expectation as (name, ok, detail). Keys: fires, never, limits, max_shown, no_leak, flags, saw."""
    interventions = [e for e in events if e.kind == TimelineKind.INTERVENTION]
    results: list[tuple[str, bool, str]] = []
    for want in expect.get("fires", []):
        hit = next((e for e in interventions if _matches(e, want)), None)
        detail = f"at {hit.t // 1000} s" if hit else "never fired"
        results.append((f"fires {_describe(want)}", hit is not None, detail))
    for trigger in expect.get("never", []):
        hits = [e.t // 1000 for e in interventions if e.payload["trigger"] == trigger]
        results.append((f"never {trigger}", not hits, f"fired at {hits} s" if hits else "ok"))
    for limit in expect.get("limits", []):
        count = sum(1 for e in interventions if e.payload["trigger"] == limit["trigger"])
        results.append(
            (f"{limit['trigger']} at most {limit['max']}", count <= limit["max"], f"{count} times")
        )
    if "max_shown" in expect:
        shown = [e for e in interventions if _unsolicited(e) and not e.payload["suppressed"]]
        ok = len(shown) <= expect["max_shown"]
        results.append((f"at most {expect['max_shown']} shown", ok, f"{len(shown)} shown"))
    if expect.get("no_leak") and reference:
        leaks = [e.payload["text"] for e in interventions if leak_reason(e.payload["text"], reference)]
        results.append(("no leak", not leaks, f"leaked: {leaks[:1]}" if leaks else "ok"))
    if expect.get("flags"):
        kinds = {e.payload["kind"] for e in events if e.kind == TimelineKind.INTEGRITY}
        missing = sorted(set(expect["flags"]) - kinds)
        results.append((f"flags {expect['flags']}", not missing, f"missing {missing}" if missing else "ok"))
    for want in expect.get("saw", []):
        hit = next((e for e in events if e.kind == TimelineKind.ANALYSIS and _saw(e, want)), None)
        detail = f"at {hit.t // 1000} s" if hit else "no analysis showed it"
        results.append((f"analyzer saw {_describe(want)}", hit is not None, detail))
    return results


def _as_set(value: Any) -> set[str]:
    return {value} if isinstance(value, str) else set(value)


def _matches(event: TimelineEvent, want: dict[str, Any]) -> bool:
    p = event.payload
    if p["trigger"] not in _as_set(want["trigger"]):
        return False
    if "step_id" in want and p["step_id"] not in _as_set(want["step_id"]):
        return False
    return "by_t" not in want or event.t <= want["by_t"]


def _saw(event: TimelineEvent, want: dict[str, Any]) -> bool:
    if "by_t" in want and event.t > want["by_t"]:
        return False
    if "issue" in want:
        return any(i["kind"] in _as_set(want["issue"]) for i in event.payload["issues"])
    statuses = {s["step_id"]: s["status"] for s in event.payload["steps"]}
    return statuses.get(want["step_id"]) in _as_set(want["status"])


def _unsolicited(event: TimelineEvent) -> bool:
    return event.payload["trigger"] not in NOT_UNSOLICITED


def _describe(want: dict[str, Any]) -> str:
    parts = [str(want.get("trigger") or want.get("issue") or want.get("step_id"))]
    if "step_id" in want and "trigger" in want:
        parts.append(f"on {want['step_id']}")
    if "status" in want:
        parts.append(f"as {want['status']}")
    if "by_t" in want:
        parts.append(f"by {want['by_t'] // 1000} s")
    return " ".join(parts)


# --- all evals -------------------------------------------------------------------------------------------------------


async def run_evals(
    evals: Sequence[Eval], model: StructuredModel, runner: Callable[[], Runner], runs: int = RUNS
) -> dict[str, list[RunReport]]:
    """Each eval's runs side by side (separate sessions), one eval after another."""
    bank = ProblemBank.load(PROBLEMS)
    results: dict[str, list[RunReport]] = {}
    for spec in evals:
        results[spec.name] = list(
            await asyncio.gather(*(run_once(spec, bank, model, runner) for _ in range(runs)))
        )
        print(summary_line(spec.name, results[spec.name]), flush=True)
    return results


def eval_passed(reports: Sequence[RunReport]) -> bool:
    return sum(r.passed for r in reports) >= min(PASS_RUNS, len(reports))


def summary_line(name: str, reports: Sequence[RunReport]) -> str:
    verdict = "PASS" if eval_passed(reports) else "FAIL"
    return f"{verdict}  {name}: {sum(r.passed for r in reports)}/{len(reports)} runs"


def write_results(results: dict[str, list[RunReport]], path: Path) -> None:
    lines = [f"# Coding evals, {datetime.now(UTC):%Y-%m-%d %H:%M} UTC", ""]
    passed = sum(eval_passed(r) for r in results.values())
    lines += [f"**{passed} of {len(results)} evals pass** (each needs {PASS_RUNS} of its runs).", ""]
    for name, reports in results.items():
        lines += [f"## {summary_line(name, reports)}", ""]
        for i, r in enumerate(reports, start=1):
            state = "pass" if r.passed else "fail"
            lines.append(f"- Run {i} ({state}, {r.analyses} analyses, {r.seconds:.0f} s real):")
            if r.error:
                lines.append(f"  - error: {r.error}")
            for name_, ok, detail in r.checks:
                lines.append(f"  - {'✓' if ok else '✗'} {name_}: {detail}")
            fired = [
                f"{i['t'] // 1000}s {i['trigger']}/{i['level']}{'/' + i['step_id'] if i['step_id'] else ''}"
                for i in r.interventions
            ]
            lines.append(f"  - interventions: {', '.join(fired) or 'none'}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def local_runner() -> Runner:
    """Candidate code runs here, in this venv: evals don't need Modal."""
    from crucible.runner.local import LocalRunner

    return LocalRunner(
        Settings(_env_file=None, RUNNER="local", ALLOW_LOCAL_RUNNER=True, LOCAL_RUNNER_ISOLATE=False)  # type: ignore[call-arg]
    )


def main(argv: Sequence[str] | None = None) -> int:
    from crucible.config import get_settings
    from crucible.main import ROLE_ENV
    from crucible.models.llm import LLM, LLMSettings

    parser = argparse.ArgumentParser(prog="python -m tests.evals.runner")
    parser.add_argument("--only", help="run evals whose name contains this")
    parser.add_argument("--runs", type=int, default=RUNS)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    s = get_settings()
    if not s.has_meta_key:
        print("MODEL_API_KEY isn't set; evals need the real models.", file=sys.stderr)
        return 2
    model = LLM(
        LLMSettings(
            api_key=s.MODEL_API_KEY,
            base_url=s.META_BASE_URL,
            role_models={role: getattr(s, env) for role, env in ROLE_ENV.items()},
        )
    )
    evals = find_evals(only=args.only)
    if not evals:
        print("no evals found", file=sys.stderr)
        return 2
    results = asyncio.run(run_evals(evals, model, local_runner, runs=args.runs))
    out = RESULTS / f"{datetime.now(UTC):%Y-%m-%d-%H%M}.md"
    write_results(results, out)
    print(f"results: {out.relative_to(REPO)}")
    return 0 if all(eval_passed(r) for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
