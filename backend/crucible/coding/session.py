"""Coding mode: how a coding session plugs into the hub (PLAN §10.1).

`CodingMode` plans sessions from the problem bank; `CodingController` runs each live one. So far: phase rules,
time limits, a straight path to `clarify`, and the problem's rubric attached there so the analyzer runs.
COD-2 adds the intro, timers and wrap-up; COD-3 handles Run and Submit.
"""

import random
from collections.abc import Mapping

from crucible.coding.problems import ProblemBank
from crucible.contracts.common import Difficulty, Phase, SessionConfig
from crucible.contracts.events import TimelineEvent
from crucible.contracts.report import CodingExtra
from crucible.contracts.ws import ClientMessage
from crucible.engine.context import RubricContext
from crucible.engine.hub import SessionPlan, SessionRuntime, SessionSetupError

DEFAULT_TIME_LIMIT_MIN: dict[Difficulty, int] = {
    Difficulty.EASY: 20,
    Difficulty.MEDIUM: 30,
    Difficulty.HARD: 40,
}
TRANSITIONS: dict[Phase, set[Phase]] = {
    Phase.SETUP: {Phase.INTRO},
    Phase.INTRO: {Phase.CLARIFY},
    Phase.CLARIFY: {Phase.CODING},
    Phase.CODING: {Phase.WRAP_UP},
    Phase.WRAP_UP: {Phase.ENDED},
}
# The analyzer watches these phases (§10.1); setup and intro have nothing to grade yet.
_WATCHED = {Phase.CLARIFY, Phase.CODING, Phase.WRAP_UP}


class CodingMode:
    """What the hub is given for coding mode."""

    def __init__(self, problems: ProblemBank, rng: random.Random | None = None) -> None:
        self.problems = problems
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
        return CodingController(self.problems)


class CodingController:
    def __init__(self, problems: ProblemBank) -> None:
        self._problems = problems

    def allowed_transitions(self) -> Mapping[Phase, set[Phase]]:
        return TRANSITIONS

    async def on_start(self, rt: SessionRuntime) -> None:
        await rt.set_phase(Phase.INTRO, "session started")
        # TODO(COD-2): present the problem first, then move on after the intro line (or 30 s).
        await rt.set_phase(Phase.CLARIFY, "intro done")
        await self._attach(rt)

    async def on_resume(self, rt: SessionRuntime) -> None:
        if rt.session.phase in _WATCHED:
            await self._attach(rt)

    async def on_client_message(self, rt: SessionRuntime, msg: ClientMessage) -> bool:
        return False  # TODO(COD-3): code.run and code.submit

    async def on_timeline(self, rt: SessionRuntime, event: TimelineEvent) -> None:
        return None  # TODO(COD-2): clarify → coding on the first 3 non-blank lines

    async def report_extra(self, rt: SessionRuntime) -> CodingExtra:
        # TODO(COD-5): final step statuses, approach and the complexity answer.
        return CodingExtra(
            problem_slug=rt.session.problem_slug or "", steps=[], approach=None, complexity_answer_ok=None
        )

    async def _attach(self, rt: SessionRuntime) -> None:
        spec = self._problems.get(rt.session.problem_slug)
        if spec is not None:
            await rt.attach(RubricContext.from_problem(spec))
