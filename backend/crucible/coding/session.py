"""Coding mode: how a coding session plugs into the hub (PLAN §10.1).

`CodingMode` plans sessions from the problem bank; `CodingController` runs each live one:
- **intro → clarify:** the interviewer presents the problem, then the rubric is attached so the analyzer runs;
- **clarify → coding:** "Start coding", or the first 3 new non-blank lines;
- **coding → wrap_up:** a submit that passes every test, "I'm done", or the time limit;
- **wrap_up → ended:** after the rubric's wrap-up questions are answered, or 3 minutes;
- along the way: Run/Submit (COD-3) and integrity notes for pastes and tab switches (COD-4).
"""

import asyncio
import contextlib
import logging
import math
import random
from collections import Counter
from collections.abc import Callable, Coroutine, Mapping
from typing import Any

from crucible.coding.integrity import IntegrityDetector
from crucible.coding.problems import ProblemBank
from crucible.coding.prompts import PHASE_LINES
from crucible.coding.tests import RunService, all_passed
from crucible.contracts.coding import Analysis, ProblemSpec
from crucible.contracts.common import Difficulty, Phase, SessionConfig
from crucible.contracts.events import (
    EditorEvent,
    InterventionLevel,
    InterventionTrigger,
    TimelineEvent,
    TimelineKind,
)
from crucible.contracts.report import CodingExtra
from crucible.contracts.ws import ClientMessage, CodeRun, CodeSubmit, IntegrityMsg
from crucible.engine.context import RubricContext
from crucible.engine.hub import SessionPlan, SessionRuntime, SessionSetupError
from crucible.engine.interviewer import say
from crucible.runner.base import Runner

logger = logging.getLogger(__name__)

DEFAULT_TIME_LIMIT_MIN: dict[Difficulty, int] = {
    Difficulty.EASY: 20,
    Difficulty.MEDIUM: 30,
    Difficulty.HARD: 40,
}
TRANSITIONS: dict[Phase, set[Phase]] = {
    Phase.SETUP: {Phase.INTRO},
    Phase.INTRO: {Phase.CLARIFY},
    Phase.CLARIFY: {Phase.CODING, Phase.WRAP_UP},  # wrap_up only when time runs out before any coding
    Phase.CODING: {Phase.WRAP_UP},
    Phase.WRAP_UP: {Phase.ENDED},
}
# The analyzer watches clarify and coding. It's detached for the wrap-up, where the questions are scripted.
_WATCHED = {Phase.CLARIFY, Phase.CODING}
# Coding before stating a plan is allowed (just noted), so Run works from clarify on.
_CAN_RUN = {Phase.CLARIFY, Phase.CODING, Phase.WRAP_UP}
STARTED_CODING_LINES = 3  # new non-blank lines that count as "started coding" (§10.1)
WRAP_UP_LIMIT_S = 180
TIMER_TICK_S = 0.5
# Reasons recorded on the phase change into wrap_up; the opener line depends on which one it was.
REASON_PASSED = "submit passed every test"
REASON_TIME = "time's up"
_OPENERS = {REASON_PASSED: "wrap_up_passed", REASON_TIME: "wrap_up_time"}


class CodingMode:
    """What the hub is given for coding mode."""

    def __init__(
        self,
        problems: ProblemBank,
        runner: Runner | Callable[[], Runner] | None = None,
        rng: random.Random | None = None,
        *,
        wrap_up_limit_s: float = WRAP_UP_LIMIT_S,
    ) -> None:
        """`runner` (or a factory for it) runs Run/Submit; None means sessions can't run code."""
        self.problems = problems
        self.runner = runner
        self.wrap_up_limit_s = wrap_up_limit_s
        self._rng = rng

    async def plan_session(self, config: SessionConfig) -> SessionPlan:
        if config.problem_slug:
            spec = self.problems.get(config.problem_slug)
            if spec is None:
                raise SessionSetupError(f"There's no problem called {config.problem_slug}.")
        else:
            spec = self.problems.pick(config.difficulty, config.topic, self._rng)
            if spec is None and len(self.problems):
                raise SessionSetupError("No problem matches that difficulty and topic.")
        minutes = (
            spec.time_limit_min if spec else DEFAULT_TIME_LIMIT_MIN[config.difficulty or Difficulty.MEDIUM]
        )
        return SessionPlan(
            problem_slug=spec.slug if spec else None,
            project_id=None,
            time_limit_s=config.time_limit_s or minutes * 60,
        )

    def __call__(self) -> "CodingController":
        runs = RunService(self.runner) if self.runner is not None else None
        return CodingController(self.problems, runs, wrap_up_limit_s=self.wrap_up_limit_s)


class CodingController:
    def __init__(
        self,
        problems: ProblemBank,
        runs: RunService | None = None,
        *,
        wrap_up_limit_s: float = WRAP_UP_LIMIT_S,
    ) -> None:
        self._problems = problems
        self._runs = runs
        self._wrap_up_limit_s = wrap_up_limit_s
        self._integrity = IntegrityDetector()
        self._tasks: set[asyncio.Task[None]] = set()
        self._timer: asyncio.Task[None] | None = None
        self._wrap_lock = asyncio.Lock()
        self._wrap_started_ms: int | None = None
        self._wrap_asked = 0  # wrap-up questions asked so far
        self._wrap_waiting = False  # a question is out and the next candidate turn answers it

    # --- ModeController -------------------------------------------------------------------------------

    def allowed_transitions(self) -> Mapping[Phase, set[Phase]]:
        return TRANSITIONS

    async def on_start(self, rt: SessionRuntime) -> None:
        await rt.set_phase(Phase.INTRO, "session started")
        await say(rt, self._intro_line(rt), InterventionTrigger.PHASE, InterventionLevel.INFO)
        await rt.set_phase(Phase.CLARIFY, "intro done")
        await self._attach(rt)
        self._start_timer(rt)

    async def on_resume(self, rt: SessionRuntime) -> None:
        if rt.session.phase in _WATCHED:
            await self._attach(rt)
        elif rt.session.phase == Phase.WRAP_UP:
            await self._restore_wrap_up(rt)
        self._start_timer(rt)

    async def on_close(self, rt: SessionRuntime) -> None:
        """Optional hub hook (PLAN §9.1): stop the timer and any wrap-up step still running."""
        tasks = [*self._tasks, *([self._timer] if self._timer else [])]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def on_client_message(self, rt: SessionRuntime, msg: ClientMessage) -> bool:
        if not isinstance(msg, CodeRun | CodeSubmit):
            return False
        spec = self._spec(rt)
        sender = rt.sender
        if spec is None or self._runs is None or rt.session.phase not in _CAN_RUN:
            reason = (
                "this session has no problem to test against"
                if spec is None
                else "code can't run in this session"
                if self._runs is None
                else f"you can't run code during {rt.session.phase}"
            )
            if sender is not None:
                await rt.error(sender, "cannot_run", f"Can't run right now: {reason}.")
            return True
        if self._runs.busy:
            if sender is not None:
                await rt.error(sender, "busy", "Your last run is still going.", retryable=True)
            return True
        kind = "submit" if isinstance(msg, CodeSubmit) else "run"
        result = await self._runs.run(rt, spec, kind, msg.file, msg.code)
        if (
            result is not None
            and kind == "submit"
            and all_passed(result)
            and rt.session.phase == Phase.CODING
        ):
            await rt.set_phase(Phase.WRAP_UP, REASON_PASSED)
        return True

    async def on_timeline(self, rt: SessionRuntime, event: TimelineEvent) -> None:
        if event.kind == TimelineKind.EDITOR:
            await self._on_edit(rt, EditorEvent.model_validate(event.payload))
        elif event.kind == TimelineKind.PHASE and event.payload["to_phase"] == Phase.WRAP_UP:
            # In a task, so the hub broadcasts the new phase before the interviewer starts the wrap-up.
            self._spawn(rt, self._begin_wrap_up(rt, event.payload["reason"]))
        elif event.kind == TimelineKind.TRANSCRIPT and rt.session.phase == Phase.WRAP_UP:
            p = event.payload
            if p["speaker"] == "candidate" and p["final"] and p["text"].strip() and self._wrap_waiting:
                self._spawn(rt, self._next_wrap_up_question(rt))

    async def report_extra(self, rt: SessionRuntime) -> CodingExtra:
        """The latest analysis's step statuses and approach (PLAN §7.5)."""
        events = await rt.timeline.read({TimelineKind.ANALYSIS})
        analyses = [Analysis.model_validate(e.payload) for e in events]
        latest = analyses[-1] if analyses else None
        approach = next((a.chosen_approach for a in reversed(analyses) if a.chosen_approach), None)
        # TODO(COD-5): grade the complexity wrap-up answer.
        return CodingExtra(
            problem_slug=rt.session.problem_slug or "",
            steps=latest.steps if latest else [],
            approach=approach,
            complexity_answer_ok=None,
        )

    # --- edits: integrity notes and "started coding" -------------------------------------------------------

    async def _on_edit(self, rt: SessionRuntime, edit: EditorEvent) -> None:
        flag = self._integrity.observe(edit)
        if flag is not None:
            await rt.record(TimelineKind.INTEGRITY, flag, t=flag.t)
            await rt.broadcast(IntegrityMsg(type="integrity.flag", flag=flag))
        if rt.session.phase == Phase.CLARIFY and edit.kind in ("change", "paste"):
            spec = self._spec(rt)
            starter = spec.starter_code if spec else ""
            if new_lines(starter, rt.code.code(edit.file)) >= STARTED_CODING_LINES:
                await rt.set_phase(Phase.CODING, "started coding")

    # --- wrap-up ------------------------------------------------------------------------------------------

    async def _begin_wrap_up(self, rt: SessionRuntime, reason: str) -> None:
        async with self._wrap_lock:
            await rt.detach()
            self._wrap_started_ms = rt.now_ms()
            self._wrap_asked = 0
            await say(
                rt,
                PHASE_LINES[_OPENERS.get(reason, "wrap_up_done")],
                InterventionTrigger.PHASE,
                InterventionLevel.INFO,
            )
            await self._ask_or_close(rt)

    async def _next_wrap_up_question(self, rt: SessionRuntime) -> None:
        async with self._wrap_lock:
            if not self._wrap_waiting or rt.session.phase != Phase.WRAP_UP:
                return  # two answers raced; the first one already moved on
            self._wrap_waiting = False
            await self._ask_or_close(rt)

    async def _ask_or_close(self, rt: SessionRuntime) -> None:
        questions = self._wrap_up_questions(rt)
        if self._wrap_asked < len(questions):
            await say(rt, questions[self._wrap_asked], InterventionTrigger.PHASE, InterventionLevel.QUESTION)
            self._wrap_asked += 1
            self._wrap_waiting = True
        else:
            await self._close(rt, "wrap-up answered")

    async def _close(self, rt: SessionRuntime, reason: str) -> None:
        self._wrap_waiting = False
        await say(rt, PHASE_LINES["closing"], InterventionTrigger.PHASE, InterventionLevel.INFO)
        await rt.end(reason)

    async def _restore_wrap_up(self, rt: SessionRuntime) -> None:
        """Reopened during the wrap-up: count the questions already asked and wait for the next answer."""
        asked = [
            e
            for e in await rt.timeline.read({TimelineKind.INTERVENTION})
            if e.payload["trigger"] == InterventionTrigger.PHASE
            and e.payload["level"] == InterventionLevel.QUESTION
        ]
        self._wrap_started_ms = asked[0].t if asked else rt.now_ms()
        self._wrap_asked = len(asked)
        self._wrap_waiting = bool(asked)
        if not asked:
            self._spawn(rt, self._begin_wrap_up(rt, ""))

    # --- timer ------------------------------------------------------------------------------------------

    def _start_timer(self, rt: SessionRuntime) -> None:
        if self._timer is None or self._timer.done():
            self._timer = asyncio.create_task(self._run_timer(rt), name=f"coding-timer-{rt.session.id}")

    async def _run_timer(self, rt: SessionRuntime) -> None:
        """Time limit → wrap_up; wrap-up limit → closing line and end (§10.1)."""
        while rt.live:
            await asyncio.sleep(TIMER_TICK_S)
            try:
                phase = rt.session.phase
                if phase in (Phase.CLARIFY, Phase.CODING) and rt.remaining_s() == 0:
                    await rt.set_phase(Phase.WRAP_UP, REASON_TIME)
                elif (
                    phase == Phase.WRAP_UP
                    and self._wrap_started_ms is not None
                    and rt.now_ms() - self._wrap_started_ms >= self._wrap_up_limit_s * 1000
                ):
                    async with self._wrap_lock:
                        if rt.live:
                            await self._close(rt, "wrap-up time limit")
            except Exception:  # task boundary: a failed tick must not stop the clock
                logger.exception("coding timer tick failed in %s", rt.session.id)

    # --- helpers ------------------------------------------------------------------------------------------

    def _spec(self, rt: SessionRuntime) -> ProblemSpec | None:
        return self._problems.get(rt.session.problem_slug)

    def _intro_line(self, rt: SessionRuntime) -> str:
        spec = self._spec(rt)
        title = spec.title if spec else "on the left"
        minutes = max(1, math.ceil(rt.session.time_limit_s / 60))
        return PHASE_LINES["intro"].format(title=title, minutes=minutes)

    def _wrap_up_questions(self, rt: SessionRuntime) -> list[str]:
        spec = self._spec(rt)
        return spec.rubric.wrap_up_questions if spec else []

    async def _attach(self, rt: SessionRuntime) -> None:
        spec = self._spec(rt)
        if spec is not None:
            await rt.attach(RubricContext.from_problem(spec))

    def _spawn(self, rt: SessionRuntime, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(self._guard(rt, coro), name=f"coding-{rt.session.id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _guard(self, rt: SessionRuntime, coro: Coroutine[Any, Any, None]) -> None:
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception:  # task boundary: a failed step leaves a note instead of a silent stall
            logger.exception("coding step failed in %s", rt.session.id)
            await rt.note("error", "a coding-session step failed; see the server log")


def new_lines(starter: str, code: str) -> int:
    """Non-blank lines in `code` that aren't in the starter code (counted with repeats)."""
    have = Counter(line.strip() for line in code.splitlines() if line.strip())
    base = Counter(line.strip() for line in starter.splitlines() if line.strip())
    return sum((have - base).values())
