"""The analyzer: when to look at the candidate's work, and what to show the model (PLAN §9.4).

`due()` decides when (a pure function, so tests drive it with numbers). `build_messages()` builds the
prompt, static parts first so cached-input pricing can apply. `Analyzer` runs both, one call at a time.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

from pydantic import BaseModel

from crucible.contracts.coding import Analysis
from crucible.contracts.events import Intervention, RunResult, TimelineEvent, TimelineKind, TranscriptTurn
from crucible.engine.codestate import TEXT_KINDS
from crucible.engine.context import RubricContext
from crucible.engine.prompts import PROMPTS

if TYPE_CHECKING:
    from crucible.engine.hub import SessionRuntime

logger = logging.getLogger(__name__)

ANALYZER_TIMEOUT_S = 12  # PLAN §21; the model wrapper enforces it per attempt
CALL_DEADLINE_S = 30  # outer guard for one tick, covering the wrapper's single retry
PAUSE_MS = 2_500  # typing paused this long → look (§9.4)
MIN_GAP_MS = 8_000  # at most one analysis per 8 s; asks skip the wait
STEADY_CHANGE_MS = 30_000  # still typing after 30 s → look anyway
TICK_S = 0.5
TRANSCRIPT_WINDOW_MS = 90_000
RUNS_SHOWN = 3

Reason = Literal["ask", "run", "turn", "pause", "steady_change"]


class StructuredModel(Protocol):
    """The slice of `crucible.models.llm.LLM` the engine uses: the analyzer, interviewer and report."""

    async def complete_json[T: BaseModel](
        self,
        role: Literal["analyzer", "interviewer"],
        messages: Sequence[Mapping[str, Any]],
        schema: type[T],
        *,
        session_id: str | None = None,
    ) -> T: ...

    async def complete_json_with_model[T: BaseModel](
        self,
        role: Literal["report"],
        messages: Sequence[Mapping[str, Any]],
        schema: type[T],
        *,
        session_id: str | None = None,
    ) -> tuple[T, str]: ...


@dataclass(slots=True)
class SchedulerState:
    last_edit_ms: int | None = None  # session time of the latest edit or snapshot
    first_change_ms: int | None = None  # first change since the last analysis started
    last_started_ms: int | None = None  # when the last analysis started
    pending: set[Literal["ask", "run", "turn"]] = field(default_factory=set)


def due(state: SchedulerState, now_ms: int, code_changed: bool) -> Reason | None:
    """Why an analysis should start now, or None. Single-flight is the caller's job."""
    if "ask" in state.pending:
        return "ask"  # a direct question skips the 8 s floor
    if state.last_started_ms is not None and now_ms - state.last_started_ms < MIN_GAP_MS:
        return None
    if "run" in state.pending:
        return "run"
    if "turn" in state.pending:
        return "turn"
    if not code_changed:
        return None
    if state.last_edit_ms is not None and now_ms - state.last_edit_ms >= PAUSE_MS:
        return "pause"
    if state.first_change_ms is not None and now_ms - state.first_change_ms >= STEADY_CHANGE_MS:
        return "steady_change"
    return None


@dataclass(frozen=True, slots=True)
class AnalysisInput:
    """Everything dynamic the analyzer sees on one tick."""

    phase: str
    elapsed_s: int
    remaining_s: int | None
    feedback: str
    files: dict[str, str]
    diffs: dict[str, str]
    runs: list[RunResult]
    transcript: list[TranscriptTurn]
    previous: Analysis | None
    interventions: list[Intervention]


def build_messages(context: RubricContext, view: AnalysisInput) -> list[dict[str, str]]:
    """System prompt, then the problem (the same all session), then this tick's state."""
    return [
        {"role": "system", "content": PROMPTS["analyzer_system"]},
        {"role": "user", "content": _problem_block(context)},
        {"role": "user", "content": _state_block(view)},
    ]


class Analyzer:
    """Watches one session's events and runs the analyzer model when `due()` says so, one call at a time."""

    def __init__(
        self,
        rt: SessionRuntime,
        context: RubricContext,
        model: StructuredModel,
        on_analysis: Callable[[Analysis], Awaitable[None]],
    ) -> None:
        self.state = SchedulerState()
        self.previous: Analysis | None = None
        self._rt = rt
        self._context = context
        self._model = model
        self._on_analysis = on_analysis
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name=f"analyzer-{self._rt.session.id}")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def on_event(self, event: TimelineEvent) -> None:
        now = self._rt.now_ms()
        typed = event.kind == TimelineKind.EDITOR and event.payload.get("kind") in TEXT_KINDS
        if typed or event.kind == TimelineKind.SNAPSHOT:
            self._changed(now)
        elif event.kind == TimelineKind.RUN:
            self.state.pending.add("run")
        elif event.kind == TimelineKind.TRANSCRIPT and event.payload["speaker"] == "candidate":
            if not event.payload["final"]:
                return
            self.state.pending.add("ask" if event.payload["source"] == "text" else "turn")
        else:
            return
        self._wake.set()

    async def run(self, reason: Reason) -> Analysis | None:
        """One analysis. On a timeout or model error, skip the tick and leave a system note."""
        rt = self._rt
        view = self._view()
        messages = build_messages(self._context, view)
        analyzed_before = dict(rt.code.code_at_last_analysis)
        self.state.last_started_ms = rt.now_ms()
        self.state.pending.clear()
        self.state.first_change_ms = None
        rt.code.mark_analyzed()
        try:
            async with asyncio.timeout(CALL_DEADLINE_S):
                analysis = await self._model.complete_json(
                    "analyzer", messages, Analysis, session_id=rt.session.id
                )
        except Exception:  # task boundary: any model failure skips this tick (§9.4)
            logger.exception("analysis failed for %s (%s)", rt.session.id, reason)
            rt.code.code_at_last_analysis = analyzed_before  # look again at the same changes next time
            await rt.note("warning", f"analysis skipped ({reason}): the model didn't answer")
            return None
        await rt.record(TimelineKind.ANALYSIS, analysis)
        self.previous = analysis
        await self._on_analysis(analysis)
        return analysis

    def _changed(self, now: int) -> None:
        self.state.last_edit_ms = now
        if self.state.first_change_ms is None:
            self.state.first_change_ms = now

    async def _loop(self) -> None:
        while True:
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(TICK_S):
                    await self._wake.wait()
            self._wake.clear()
            reason = due(self.state, self._rt.now_ms(), self._rt.code.changed_since_analysis())
            if reason is not None:
                await self.run(reason)

    def _view(self) -> AnalysisInput:
        rt = self._rt
        now = rt.now_ms()
        files = {f: rt.code.code(f) for f in self._context.files}
        return AnalysisInput(
            phase=rt.session.phase,
            elapsed_s=now // 1000,
            remaining_s=rt.remaining_s(),
            feedback=rt.session.config.feedback,
            files=files,
            diffs={f: d for f in files if (d := rt.code.diff_since_analysis(f))},
            runs=[RunResult.model_validate(e.payload) for e in rt.timeline.tail([TimelineKind.RUN])][
                -RUNS_SHOWN:
            ],
            transcript=[
                TranscriptTurn.model_validate(e.payload)
                for e in rt.timeline.tail([TimelineKind.TRANSCRIPT], since_t=now - TRANSCRIPT_WINDOW_MS)
                if e.payload["final"]
            ],
            previous=self.previous,
            interventions=[
                Intervention.model_validate(e.payload)
                for e in rt.timeline.tail([TimelineKind.INTERVENTION])
                if not e.payload["suppressed"]
            ],
        )


# --- prompt blocks -------------------------------------------------------------------------------------------


def _problem_block(context: RubricContext) -> str:
    steps = "\n".join(
        f"- {s.id} (order {s.order}, {'required' if s.required else 'optional'}): {s.title}. {s.description}\n"
        f"  Look for: {'; '.join(s.look_for)}\n"
        f"  Hints by level: nudge: {s.hints[0] if s.hints else ''} | question: "
        f"{s.hints[1] if len(s.hints) > 1 else ''} | hint: {s.hints[2] if len(s.hints) > 2 else ''}"
        for s in context.steps
    )
    edge_cases = "\n".join(f"- {e.id}: {e.description}" for e in context.edge_cases) or "- none listed"
    mistakes = "\n".join(
        f"- {m.id}: {m.description} (looks like: {m.symptom})" for m in context.common_mistakes
    )
    return (
        f"# Problem: {context.title}\n\n{context.brief_md}\n\n"
        f"## Rubric steps\n{steps}\n\n"
        f"## Edge cases\n{edge_cases}\n\n"
        f"## Common mistakes\n{mistakes or '- none listed'}"
    )


def _state_block(view: AnalysisInput) -> str:
    remaining = (
        "no limit"
        if view.remaining_s is None
        else f"{view.remaining_s // 60}:{view.remaining_s % 60:02d} left"
    )
    elapsed = f"{view.elapsed_s // 60}:{view.elapsed_s % 60:02d}"
    parts = [
        "# Now",
        f"Phase: {view.phase}. Elapsed {elapsed}, {remaining}. Feedback mode: {view.feedback}.",
    ]
    for name, code in view.files.items():
        parts.append(f"## Code: {name}\n```python\n{_numbered(code)}\n```")
    for name, diff in view.diffs.items():
        parts.append(f"## Changes since your last look: {name}\n```diff\n{diff}\n```")
    parts.append("## Recent test runs\n" + ("\n".join(_run_line(r) for r in view.runs) or "None yet."))
    parts.append(
        "## What the candidate said (last 90 s)\n"
        + (
            "\n".join(
                f"- [{_clock(t.start_ms)}] {t.text}" for t in view.transcript if t.speaker == "candidate"
            )
            or "Nothing."
        )
    )
    if view.previous is not None:
        parts.append(
            "## Your previous step statuses\n"
            + "\n".join(f"- {s.step_id}: {s.status}" for s in view.previous.steps)
        )
    if view.interventions:
        parts.append(
            "## Already said to the candidate (don't repeat)\n"
            + "\n".join(f"- [{i.trigger}, {i.level}, step {i.step_id}] {i.text}" for i in view.interventions)
        )
    return "\n\n".join(parts)


def _run_line(run: RunResult) -> str:
    # Hidden tests appear as counts only: their inputs must never reach a prompt that could echo them.
    visible = [c for c in run.cases if c.visible]
    hidden = [c for c in run.cases if not c.visible]
    line = f"- {run.kind} at {_clock(run.t)}: {run.passed}/{run.total} passed"
    if run.compile_error:
        line += f"; compile error: {run.compile_error[:200]}"
    if run.timed_out:
        line += "; timed out"
    for case in visible:
        if not case.passed:
            line += (
                f"\n  - visible test {case.id} failed: input {case.input_repr}, expected {case.expected_repr}, "
                f"got {case.actual_repr}" + (f" ({case.error})" if case.error else "")
            )
    if hidden:
        line += f"\n  - hidden tests: {sum(c.passed for c in hidden)}/{len(hidden)} passed"
    return line


def _numbered(code: str) -> str:
    return "\n".join(f"{i:>3} | {line}" for i, line in enumerate(code.splitlines(), start=1)) or "  (empty)"


def _clock(ms: int) -> str:
    seconds = max(0, ms) // 1000
    return f"{seconds // 60:02d}:{seconds % 60:02d}"
