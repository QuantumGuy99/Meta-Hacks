"""Coding mode's controller: how a coding session plugs into the hub (PLAN §10.1).

This is the ENG-1 minimum: phase rules, the default time limit and a straight path to `clarify`. COD-1 picks
the problem, COD-2 adds the intro, timers and wrap-up, COD-3 handles Run and Submit.
"""

from collections.abc import Mapping

from crucible.contracts.common import Difficulty, Phase, SessionConfig
from crucible.contracts.events import TimelineEvent
from crucible.contracts.report import CodingExtra
from crucible.contracts.ws import ClientMessage
from crucible.engine.hub import SessionPlan, SessionRuntime

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


class CodingController:
    @classmethod
    async def plan_session(cls, config: SessionConfig) -> SessionPlan:
        # TODO(COD-1): pick from the ProblemBank when only a difficulty is given, and use its time limit.
        minutes = DEFAULT_TIME_LIMIT_MIN[config.difficulty or Difficulty.MEDIUM]
        return SessionPlan(
            problem_slug=config.problem_slug,
            project_id=None,
            time_limit_s=config.time_limit_s or minutes * 60,
        )

    def allowed_transitions(self) -> Mapping[Phase, set[Phase]]:
        return TRANSITIONS

    async def on_start(self, rt: SessionRuntime) -> None:
        await rt.set_phase(Phase.INTRO, "session started")
        # TODO(COD-2): present the problem first, then move on after the intro line (or 30 s).
        await rt.set_phase(Phase.CLARIFY, "intro done")

    async def on_client_message(self, rt: SessionRuntime, msg: ClientMessage) -> bool:
        return False  # TODO(COD-3): code.run and code.submit

    async def on_timeline(self, rt: SessionRuntime, event: TimelineEvent) -> None:
        return None  # TODO(COD-2): clarify → coding on the first 3 non-blank lines

    async def report_extra(self, rt: SessionRuntime) -> CodingExtra:
        # TODO(COD-5): final step statuses, approach and the complexity answer.
        return CodingExtra(
            problem_slug=rt.session.problem_slug or "", steps=[], approach=None, complexity_answer_ok=None
        )
