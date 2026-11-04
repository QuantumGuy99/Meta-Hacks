"""Coding mode: how a coding session plugs into the hub (PLAN §10.1).

`CodingMode` plans sessions from the problem bank; `CodingController` runs each live one:
- **intro:** a short warm-up, like a real interview: the interviewer greets the candidate and asks about them, the
  model reacts to the answer with one follow-up, then moves on (after 2 answers, 90 s, 25 s of no answer, or "Skip
  intro"). The clock doesn't run yet;
- **intro → clarify:** the interviewer presents the problem, then the rubric is attached so the analyzer runs;
- **clarify → coding:** "Start coding", or the first 3 new non-blank lines;
- **coding → wrap_up:** a submit that passes every test, "I'm done", or the time limit;
- **wrap_up → ended:** after the rubric's wrap-up questions are answered, or 3 minutes; a typed answer moves on
  at once, a spoken one after a quiet gap, because Muse Voice ends a turn at every pause;
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

from crucible.coding.complexity import complexity_answer, complexity_question, grade_complexity_answer
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
from crucible.engine.interviewer import reply, say
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
# The warm-up (§3.1): the greeting plus one follow-up, and never long enough to feel like a delay.
WARM_UP_QUESTIONS = 2
WARM_UP_LIMIT_S = 90
WARM_UP_WAIT_S = 25  # no answer to a warm-up question by then: move on to the problem
TIMER_TICK_S = 0.5
# A spoken answer to a scripted question (warm-up or wrap-up) is over after this long with no new candidate
# speech. Muse Voice already ends a turn at a pause, so this only catches a second thought; longer and the
# interviewer feels slow to respond.
ANSWER_GAP_MS = 1_200
ANSWER_POLL_S = 0.1
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
        warm_up: bool = True,
        warm_up_wait_s: float = WARM_UP_WAIT_S,
        warm_up_limit_s: float = WARM_UP_LIMIT_S,
    ) -> None:
        """`runner` (or a factory for it) runs Run/Submit; None means sessions can't run code. `warm_up=False`
        goes straight to the problem (engine tests and evals, which start at clarify)."""
        self.problems = problems
        self.runner = runner
        self.wrap_up_limit_s = wrap_up_limit_s
        self.warm_up = warm_up
        self.warm_up_wait_s = warm_up_wait_s
        self.warm_up_limit_s = warm_up_limit_s
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
        return CodingController(
            self.problems,
            runs,
            wrap_up_limit_s=self.wrap_up_limit_s,
            warm_up=self.warm_up,
            warm_up_wait_s=self.warm_up_wait_s,
            warm_up_limit_s=self.warm_up_limit_s,
        )


class CodingController:
    def __init__(
        self,
        problems: ProblemBank,
        runs: RunService | None = None,
        *,
        wrap_up_limit_s: float = WRAP_UP_LIMIT_S,
        warm_up: bool = True,
        warm_up_wait_s: float = WARM_UP_WAIT_S,
        warm_up_limit_s: float = WARM_UP_LIMIT_S,
    ) -> None:
        self._problems = problems
        self._warm_up = warm_up
        self._runs = runs
        self._wrap_up_limit_s = wrap_up_limit_s
        self._warm_up_wait_s = warm_up_wait_s
        self._warm_up_limit_s = warm_up_limit_s
        self._integrity = IntegrityDetector()
        self._tasks: set[asyncio.Task[None]] = set()
        self._timer: asyncio.Task[None] | None = None
        self._wrap_lock = asyncio.Lock()
        self._wrap_started_ms: int | None = None
        self._wrap_asked = 0  # wrap-up questions asked so far
        self._wrap_waiting = False  # a question is out and the next candidate turn answers it
        self._warm_started_ms: int | None = None
        self._warm_asked = 0  # warm-up questions asked so far
        # The open warm-up question went out then: speech that began earlier isn't its answer, and turns recorded
        # before its timeline seq belong to the previous answer (they can share its millisecond).
        self._warm_asked_ms = 0
        self._warm_asked_seq = 0
        self._warm_waiting = False
        # The warm-up reply written while the pause after an answer runs: ((what they said, kind), task).
        self._warm_ahead: tuple[tuple[str, str], asyncio.Task[str | None]] | None = None
        self._problem_presented = False
        self._sandbox_closed = False  # close_session runs once, on `ended` or on_close, whichever is first
        self._heard_ms: int | None = None  # the open question's spoken answer was last heard then
        self._quiet_wait: asyncio.Task[None] | None = None  # moves on once that answer has gone quiet

    # --- ModeController -------------------------------------------------------------------------------

    def allowed_transitions(self) -> Mapping[Phase, set[Phase]]:
        return TRANSITIONS

    async def on_start(self, rt: SessionRuntime) -> None:
        self._track(asyncio.create_task(self._warm_sandbox(rt), name=f"warm-sandbox-{rt.session.id}"))
        await rt.set_phase(Phase.INTRO, "session started")
        self._start_timer(rt)
        if not self._warm_up:
            await self._start_problem(rt, "intro done")
            return
        self._warm_started_ms = rt.now_ms()
        async with self._wrap_lock:
            await self._ask_warm_up(rt, PHASE_LINES["warmup_greeting"])

    async def on_resume(self, rt: SessionRuntime) -> None:
        if rt.session.phase == Phase.INTRO:
            await self._start_problem(rt, "resumed")  # a reopened warm-up goes straight to the problem
        elif rt.session.phase in _WATCHED:
            await self._attach(rt)
        elif rt.session.phase == Phase.WRAP_UP:
            await self._restore_wrap_up(rt)
        self._start_timer(rt)

    async def on_close(self, rt: SessionRuntime) -> None:
        """Optional hub hook (PLAN §9.1): stop the timer and any wrap-up step still running."""
        tasks = [*self._tasks, *([self._timer] if self._timer else [])]
        if self._warm_ahead is not None:
            self._warm_ahead[1].cancel()
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._close_sandbox(rt)

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
        p = event.payload
        if event.kind == TimelineKind.EDITOR:
            await self._on_edit(rt, EditorEvent.model_validate(p))
        elif event.kind == TimelineKind.PHASE and p["to_phase"] == Phase.ENDED:
            self._track(asyncio.create_task(self._close_sandbox(rt), name=f"close-sandbox-{rt.session.id}"))
        elif event.kind == TimelineKind.PHASE and p["to_phase"] == Phase.WRAP_UP:
            # In a task, so the hub broadcasts the new phase before the interviewer starts the wrap-up.
            self._spawn(rt, self._begin_wrap_up(rt, p["reason"]))
        elif event.kind == TimelineKind.PHASE and (p["from_phase"], p["to_phase"]) == (
            Phase.INTRO,
            Phase.CLARIFY,
        ):
            # The warm-up is over. "Skip intro" moved the phase from the browser, so the problem comes now.
            self._warm_waiting, self._heard_ms = False, None
            if not self._problem_presented:
                self._problem_presented = True
                self._spawn(rt, self._present_problem(rt))
        elif (
            event.kind == TimelineKind.TRANSCRIPT
            and p["speaker"] == "candidate"
            and p["final"]
            and p["text"].strip()
        ):
            if rt.session.phase == Phase.WRAP_UP and self._wrap_waiting:
                self._answered(
                    rt, p["source"], Phase.WRAP_UP, lambda: self._next_wrap_up_question(rt, self._wrap_asked)
                )
            elif (
                rt.session.phase == Phase.INTRO
                and self._warm_waiting
                and p["start_ms"] >= self._warm_asked_ms
            ):
                self._write_warm_up_reply_ahead(rt)
                self._answered(
                    rt, p["source"], Phase.INTRO, lambda: self._warm_up_answered(rt, self._warm_asked)
                )

    async def report_extra(self, rt: SessionRuntime) -> CodingExtra:
        """The latest analysis's step statuses; the approach: the one the analyzer named, else the plan the
        candidate stated (the analyzer often leaves `chosen_approach` empty, PLAN §7.5); and whether the
        complexity answer matched an acceptable approach (§10.5)."""
        events = await rt.timeline.read({TimelineKind.ANALYSIS})
        analyses = [Analysis.model_validate(e.payload) for e in events]
        latest = analyses[-1] if analyses else None
        approach = next((a.chosen_approach for a in reversed(analyses) if a.chosen_approach), None) or next(
            (a.stated_plan for a in reversed(analyses) if a.stated_plan), None
        )
        return CodingExtra(
            problem_slug=rt.session.problem_slug or "",
            steps=latest.steps if latest else [],
            approach=approach,
            complexity_answer_ok=await self._grade_complexity(rt),
        )

    async def _grade_complexity(self, rt: SessionRuntime) -> bool | None:
        """None when there's nothing to grade (never asked, no answer, no model) or the grading call failed."""
        spec = self._spec(rt)
        index = complexity_question(spec.rubric.wrap_up_questions) if spec else None
        if spec is None or index is None or rt.model is None:
            return None
        events = await rt.timeline.read({TimelineKind.INTERVENTION, TimelineKind.TRANSCRIPT})
        answer = complexity_answer(events, index)
        if answer is None:
            return None
        ok = await grade_complexity_answer(rt.model, spec, answer, session_id=rt.session.id)
        if ok is None:
            await rt.note("warning", "the complexity answer couldn't be graded; the report leaves it out")
        return ok

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

    # --- warm-up and the problem ------------------------------------------------------------------------

    async def _ask_warm_up(self, rt: SessionRuntime, text: str) -> None:
        """Ask a warm-up question and wait for the answer (call with `_wrap_lock` held)."""
        line = await say(rt, text, InterventionTrigger.WARMUP, InterventionLevel.QUESTION)
        self._warm_asked += 1
        self._warm_asked_ms = line.t
        asked = rt.timeline.tail([TimelineKind.INTERVENTION], since_t=line.t)
        self._warm_asked_seq = next(e.seq for e in reversed(asked) if e.payload["id"] == line.id)
        self._warm_waiting = True

    async def _warm_up_answered(self, rt: SessionRuntime, answering: int) -> None:
        """React to the answer to warm-up question number `answering` with the model: a follow-up question after
        the first, then a closing reaction and on to the problem. Canned lines when there's no model."""
        async with self._wrap_lock:
            if not self._warm_waiting or self._warm_asked != answering or rt.session.phase != Phase.INTRO:
                return  # two answers raced, or the warm-up already ended
            self._warm_waiting, self._heard_ms = False, None
            said, kind = self._warm_said(rt), self._warm_kind(rt, answering)
            ahead, self._warm_ahead = self._warm_ahead, None
            if ahead is not None and ahead[0] == (said, kind):
                line = await ahead[1]  # written during the pause
            else:
                if ahead is not None:
                    ahead[1].cancel()
                line = await reply(rt, rt.model, kind, said) if rt.model is not None and said else None
            last = kind == "warmup_close"
            if not last:
                await self._ask_warm_up(rt, line or PHASE_LINES["warmup_follow_up"])
                return
            await say(
                rt, line or PHASE_LINES["warmup_thanks"], InterventionTrigger.WARMUP, InterventionLevel.INFO
            )
            await self._start_problem(rt, "warm-up done")

    def _write_warm_up_reply_ahead(self, rt: SessionRuntime) -> None:
        """Start the reply to the warm-up answer heard so far, so it's ready when the pause after it ends."""
        said = self._warm_said(rt)
        if rt.model is None or not said:
            return
        key = (said, self._warm_kind(rt, self._warm_asked))
        if self._warm_ahead is not None:
            if self._warm_ahead[0] == key:
                return
            self._warm_ahead[1].cancel()  # they said more: the reply must hear all of it
        task = asyncio.create_task(reply(rt, rt.model, key[1], said), name=f"warm-up-reply-{rt.session.id}")  # type: ignore[arg-type]
        self._warm_ahead = (key, task)

    def _warm_said(self, rt: SessionRuntime) -> str:
        """What the candidate said since the open warm-up question went out."""
        return " ".join(
            e.payload["text"].strip()
            for e in rt.timeline.tail([TimelineKind.TRANSCRIPT], since_t=self._warm_asked_ms)
            if e.seq > self._warm_asked_seq and e.payload["speaker"] == "candidate" and e.payload["final"]
        )

    def _warm_kind(self, rt: SessionRuntime, answering: int) -> str:
        """A follow-up question, or the closing reaction: no follow-up they wouldn't have time to answer."""
        last = answering >= WARM_UP_QUESTIONS or self._warm_up_over(rt, margin_s=self._warm_up_wait_s)
        return "warmup_close" if last else "warmup"

    async def _end_warm_up(self, rt: SessionRuntime, reason: str) -> None:
        """The warm-up ran out of time, or a question went unanswered: move on to the problem."""
        async with self._wrap_lock:
            if rt.session.phase != Phase.INTRO:
                return
            self._warm_waiting = False
            await say(rt, PHASE_LINES["warmup_move_on"], InterventionTrigger.WARMUP, InterventionLevel.INFO)
            await self._start_problem(rt, reason)

    def _warm_up_over(self, rt: SessionRuntime, *, margin_s: float = 0) -> bool:
        started = self._warm_started_ms if self._warm_started_ms is not None else 0
        return rt.now_ms() - started >= (self._warm_up_limit_s - margin_s) * 1000

    async def _start_problem(self, rt: SessionRuntime, reason: str) -> None:
        """Present the problem, start clarify (the clock starts now) and attach the analyzer."""
        self._problem_presented = True
        await say(rt, self._intro_line(rt), InterventionTrigger.PHASE, InterventionLevel.INFO)
        await rt.set_phase(Phase.CLARIFY, reason)
        await self._attach(rt)

    async def _present_problem(self, rt: SessionRuntime) -> None:
        """After "Skip intro": clarify has already started."""
        await say(rt, self._intro_line(rt), InterventionTrigger.PHASE, InterventionLevel.INFO)
        await self._attach(rt)

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

    def _answered(
        self,
        rt: SessionRuntime,
        source: str,
        phase: Phase,
        move_on: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        """A final candidate turn while a scripted question (warm-up or wrap-up) is out (§10.1). A typed answer
        moves on at once; a spoken one once it has gone quiet, since Muse Voice ends a turn at every pause: "O of n
        time" [pause] "and O of one space" comes as two turns, and each new one restarts the wait."""
        if source != "voice":
            self._spawn(rt, move_on())
            return
        self._heard_ms = rt.now_ms()
        if self._quiet_wait is None or self._quiet_wait.done():
            self._quiet_wait = self._spawn(rt, self._move_on_when_quiet(rt, phase, move_on))

    async def _move_on_when_quiet(
        self, rt: SessionRuntime, phase: Phase, move_on: Callable[[], Coroutine[Any, Any, None]]
    ) -> None:
        """Move on from the open question after ANSWER_GAP_MS with no new candidate speech.

        A turn still being spoken (the voice bridge's speechStart set "listening" and it isn't final yet) holds the
        wait. Stops once nothing is pending: something else moved on (a typed answer, a time limit). It exits
        only at the loop check, so an answer to the next question that lands meanwhile is never dropped.
        """
        while self._heard_ms is not None and rt.session.phase == phase:
            if rt.interviewer_state == "listening":
                self._heard_ms = rt.now_ms()
            wait_ms = self._heard_ms + ANSWER_GAP_MS - rt.now_ms()
            if wait_ms > 0:
                await asyncio.sleep(min(wait_ms / 1000, ANSWER_POLL_S))
            else:
                self._heard_ms = None
                await move_on()

    async def _next_wrap_up_question(self, rt: SessionRuntime, answering: int) -> None:
        """Move on from question number `answering`, unless another answer to it already did."""
        async with self._wrap_lock:
            if not self._wrap_waiting or self._wrap_asked != answering or rt.session.phase != Phase.WRAP_UP:
                return  # two answers raced; the first one already moved on
            self._wrap_waiting = False
            self._heard_ms = None
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
        self._heard_ms = None
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
                speaking = self._heard_ms is not None or rt.interviewer_state == "listening"
                if phase == Phase.INTRO and not speaking:  # never cut off an answer being spoken
                    waited_ms = rt.now_ms() - self._warm_asked_ms
                    unanswered = self._warm_waiting and waited_ms >= self._warm_up_wait_s * 1000
                    if unanswered or self._warm_up_over(rt):
                        await self._end_warm_up(rt, "warm-up time")
                elif phase in (Phase.CLARIFY, Phase.CODING) and rt.remaining_s() == 0:
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
        minutes = max(1, math.ceil((rt.remaining_s() or rt.session.time_limit_s) / 60))
        return PHASE_LINES["intro"].format(title=title, minutes=minutes)

    def _wrap_up_questions(self, rt: SessionRuntime) -> list[str]:
        spec = self._spec(rt)
        return spec.rubric.wrap_up_questions if spec else []

    async def _attach(self, rt: SessionRuntime) -> None:
        spec = self._spec(rt)
        if spec is not None:
            await rt.attach(RubricContext.from_problem(spec))

    # --- runner sandbox (COD-3 step 3) ----------------------------------------------------------------

    async def _warm_sandbox(self, rt: SessionRuntime) -> None:
        """Warm the runner's sandbox in the background, so the first Run doesn't pay the cold start
        inside its 20 s deadline. A failure is logged and ignored: Run opens the sandbox lazily."""
        if self._runs is None:
            return
        try:
            await self._runs.open_session(rt.session.id)
        except Exception:  # task boundary: warming is best-effort, never a session failure
            logger.exception("couldn't warm the sandbox for %s; the first Run will open it", rt.session.id)

    async def _close_sandbox(self, rt: SessionRuntime) -> None:
        """Close the session's sandbox, once. The runner's idle timeout is the backstop."""
        if self._runs is None or self._sandbox_closed:
            return
        try:
            await self._runs.close_session(rt.session.id)
        except Exception:  # task boundary: the sandbox also stops on its own idle timeout
            logger.exception("couldn't close the sandbox for %s", rt.session.id)
            return
        self._sandbox_closed = True

    def _track(self, task: asyncio.Task[None]) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _spawn(self, rt: SessionRuntime, coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        task = asyncio.create_task(self._guard(rt, coro), name=f"coding-{rt.session.id}")
        self._track(task)
        return task

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
