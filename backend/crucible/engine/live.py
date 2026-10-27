"""One tick of the live interviewer: analysis → notes → policy → interviewer (PLAN §4.2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from crucible.contracts.coding import Analysis
from crucible.contracts.common import FeedbackLevel
from crucible.contracts.events import TimelineEvent
from crucible.contracts.ws import NotesUpdate
from crucible.engine.analyzer import Analyzer, StructuredModel
from crucible.engine.context import RubricContext
from crucible.engine.interviewer import deliver
from crucible.engine.policy import PolicyState, decide

if TYPE_CHECKING:
    from crucible.engine.hub import SessionRuntime


class LiveEngine:
    """The analyzer, policy and interviewer for one attached rubric. Started by `rt.attach()`."""

    def __init__(self, rt: SessionRuntime, context: RubricContext, model: StructuredModel) -> None:
        self.policy = PolicyState()
        self.analyzer = Analyzer(rt, context, model, self._on_analysis)
        self._rt = rt
        self._context = context

    def start(self) -> None:
        self.analyzer.start()

    async def stop(self) -> None:
        await self.analyzer.stop()

    def on_event(self, event: TimelineEvent) -> None:
        self.analyzer.on_event(event)

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
        now = rt.now_ms()
        decision = decide(
            analysis,
            self.policy,
            steps=self._context.steps,
            now_ms=now,
            last_edit_ms=self.analyzer.state.last_edit_ms,
        )
        self.policy.previous = analysis
        if decision is None:
            return
        await deliver(rt, decision, self._context)
        self.policy.remember(decision, now)
