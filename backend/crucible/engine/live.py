"""The live interviewer: analysis → notes → policy → interviewer (PLAN §4.2).

The analyzer runs in its own task. The policy runs in one more task that owns every delivery: it ticks every
0.5 s for the time rules and wakes early for questions, hint requests, runs and analyses.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from dataclasses import replace
from typing import TYPE_CHECKING

from crucible.contracts.coding import Analysis
from crucible.contracts.common import FeedbackLevel
from crucible.contracts.events import (
    EditorEvent,
    InterventionTrigger,
    RunResult,
    TimelineEvent,
    TimelineKind,
    TranscriptTurn,
)
from crucible.contracts.ws import NotesUpdate
from crucible.engine.analyzer import TICK_S, Analyzer, StructuredModel
from crucible.engine.classifier import CONTEXT_TURNS, is_question_for_interviewer
from crucible.engine.codestate import TEXT_KINDS
from crucible.engine.context import RubricContext
from crucible.engine.interviewer import answer, deliver
from crucible.engine.policy import Facts, PolicyState, decide, is_question, written_lines

if TYPE_CHECKING:
    from crucible.engine.hub import SessionRuntime

logger = logging.getLogger(__name__)

MAX_DECISIONS_PER_TICK = 3  # e.g. an answer, a hint and a time warning that came due together


class LiveEngine:
    """The analyzer, policy and interviewer for one attached rubric. Started by `rt.attach()`."""

    def __init__(self, rt: SessionRuntime, context: RubricContext, model: StructuredModel) -> None:
        self.policy = PolicyState()
        self.analyzer = Analyzer(rt, context, model, self._on_analysis)
        self._model = model
        self._last_question: str | None = None  # what the candidate asked, not yet answered (ASKED)
        # Spoken turns already asked (Ask held, or the classifier said so), and the last few, for its context.
        self._asked_turns: set[str] = set()
        self._said: deque[str] = deque(maxlen=CONTEXT_TURNS)
        self._classifying: set[asyncio.Task[None]] = set()
        self._rt = rt
        self._context = context
        self._main = context.files[0] if context.files else "solution.py"
        self._starter: str | None = rt.code.code(self._main) or None  # set by the first snapshot otherwise
        self._phase = rt.session.phase
        self._phase_started_ms = rt.now_ms()
        self._last_edit_ms: int | None = None
        self._last_speech_ms: int | None = None
        self._last_partial_ms: int | None = None
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self.analyzer.start()
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name=f"policy-{self._rt.session.id}")

    async def stop(self) -> None:
        for task in list(self._classifying):
            task.cancel()
        self._classifying.clear()
        await self.analyzer.stop()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def on_event(self, event: TimelineEvent) -> None:
        self.analyzer.on_event(event)
        self._observe(event)

    def request_hint(self, step_id: str | None) -> None:
        self.policy.request_hint(step_id)
        self._wake.set()

    def ask(self, question: str, turn_id: str | None = None) -> None:
        """A question to the interviewer: typed in chat, spoken while holding Ask, or a spoken turn the classifier
        calls a question (§9.7). ASKED answers it.

        Questions asked before the reply are answered together: a spoken question often arrives as two turns. A
        spoken turn is asked at most once (the Ask button and the classifier can both flag it).
        """
        if turn_id is not None:
            if turn_id in self._asked_turns:
                return
            self._asked_turns.add(turn_id)
        if self._last_question:
            self._last_question = f"{self._last_question} {question}"  # one answer is already on its way
        else:
            self._last_question = question
            self.policy.ask()
        self._wake.set()

    def heard_speech(self) -> None:
        """Candidate speech in progress (a partial transcript): unsolicited messages wait until it stops.

        Partials aren't stored on the timeline (§9.7), so ENG-7's VoiceBridge calls this directly.
        """
        self._last_partial_ms = self._rt.now_ms()

    async def tick(self) -> None:
        """Ask the policy what to say now, and say it."""
        for _ in range(MAX_DECISIONS_PER_TICK):
            decision = decide(self.policy, self._facts())
            if decision is None:
                return
            if (
                decision.trigger == InterventionTrigger.ASKED
                and not decision.suppressed
                and self._last_question
            ):
                question, self._last_question = self._last_question, None
                reply = await answer(self._rt, self._model, self._context, question)
                if reply is not None:  # otherwise deliver() sends the canned line
                    decision = replace(decision, draft=reply)
            await deliver(self._rt, decision, self._context)

    async def _on_analysis(self, analysis: Analysis) -> None:
        rt = self._rt
        # Notes are feedback too, so passive mode keeps them for the report.
        if rt.session.config.feedback == FeedbackLevel.ACTIVE:
            await rt.broadcast(
                NotesUpdate(
                    type="notes.update",
                    steps=analysis.steps,
                    issues=analysis.issues,
                    stated_plan=analysis.stated_plan,
                )
            )
        self.policy.observe_analysis(analysis)
        self._wake.set()

    def _observe(self, event: TimelineEvent) -> None:
        now = self._rt.now_ms()
        match event.kind:
            case TimelineKind.EDITOR if event.payload.get("kind") in TEXT_KINDS:
                self._last_edit_ms = now
                self.policy.observe_edit(EditorEvent.model_validate(event.payload))
            case TimelineKind.SNAPSHOT if self._starter is None and event.payload["file"] == self._main:
                self._starter = event.payload["code"]  # the editor loads the starter code as a snapshot
            case TimelineKind.TRANSCRIPT if (
                event.payload["speaker"] == "candidate" and event.payload["final"]
            ):
                turn = TranscriptTurn.model_validate(event.payload)
                self._last_speech_ms = now
                if turn.source == "text" and is_question(turn.text):
                    self.ask(turn.text)
                elif turn.source == "voice":
                    self._classify(turn)
            case TimelineKind.RUN:
                self.policy.observe_run(RunResult.model_validate(event.payload))
                self._wake.set()

    def _classify(self, turn: TranscriptTurn) -> None:
        """Ask the classifier about a spoken turn in the background, so the transcript never waits on it."""
        earlier = list(self._said)
        self._said.append(turn.text)
        task = asyncio.create_task(self._classify_turn(turn, earlier), name=f"classify-{turn.turn_id}")
        self._classifying.add(task)
        task.add_done_callback(self._classifying.discard)

    async def _classify_turn(self, turn: TranscriptTurn, earlier: list[str]) -> None:
        if turn.turn_id in self._asked_turns:
            return  # held on Ask: already a question
        verdict = await is_question_for_interviewer(
            self._model, turn.text, earlier, session_id=self._rt.session.id
        )
        if verdict is None:
            await self._rt.note(
                "warning", "the voice classifier didn't answer; treated the turn as thinking aloud"
            )
        elif verdict:
            self.ask(turn.text, turn.turn_id)

    def _facts(self) -> Facts:
        rt = self._rt
        now = rt.now_ms()
        if rt.session.phase != self._phase:  # set_phase doesn't go through record(), so notice it here
            self._phase, self._phase_started_ms = rt.session.phase, now
        code = rt.code.code(self._main)
        config = rt.session.config
        return Facts(
            now_ms=now,
            phase=self._phase,
            phase_started_ms=self._phase_started_ms,
            passive=config.feedback == FeedbackLevel.PASSIVE,
            voice=config.voice,
            time_limit_s=rt.session.time_limit_s,
            steps=self._context.steps,
            code=code,
            lines_written=written_lines(self._starter or "", code),
            last_edit_ms=self._last_edit_ms,
            last_speech_ms=self._last_speech_ms,
            last_partial_ms=self._last_partial_ms,
        )

    async def _loop(self) -> None:
        while True:
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(TICK_S):
                    await self._wake.wait()
            self._wake.clear()
            try:
                await self.tick()
            except Exception:  # task boundary: one failed delivery must not silence the interviewer
                logger.exception("policy tick failed for %s", self._rt.session.id)
                await self._rt.note("error", "the interviewer couldn't deliver a message")
