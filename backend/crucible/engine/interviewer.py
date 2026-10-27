"""Turns a policy decision into what the candidate sees and hears (PLAN §9.6).

ENG-4's thin version: the code check of the leak guard and delivery. ENG-6 adds phrasing, answers to
questions, phase lines, the reference-overlap check and `say()`.
"""

from __future__ import annotations

import ast
import logging
from typing import TYPE_CHECKING

from crucible.contracts.common import FeedbackLevel
from crucible.contracts.events import Intervention, InterventionLevel, TimelineKind, TranscriptTurn
from crucible.contracts.ws import InterviewerMessage
from crucible.engine.context import RubricContext
from crucible.engine.ids import new_id
from crucible.engine.policy import Decision

if TYPE_CHECKING:
    from crucible.engine.hub import SessionRuntime

logger = logging.getLogger(__name__)

_LADDER = [InterventionLevel.NUDGE, InterventionLevel.QUESTION, InterventionLevel.HINT]
_GENERIC = "Take a step back and walk me through what you're doing."


def looks_like_code(text: str) -> bool:
    """A code fence, or two or more lines that parse as Python statements (§9.6 leak guard, code part)."""
    if "```" in text:
        return True
    return sum(_is_statement(line.strip()) for line in text.splitlines() if line.strip()) >= 2


def _is_statement(line: str) -> bool:
    # A block header ("if not xs:") only parses with a body, so give it one.
    candidates = [line, f"{line} pass"] if line.endswith(":") else [line]
    for candidate in candidates:
        try:
            tree = ast.parse(candidate)
        except SyntaxError:
            continue
        # A lone name or constant ("total", "0") is prose that happens to parse, not code.
        return any(
            not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Name | ast.Constant)) for n in tree.body
        )
    return False


def rubric_hint(context: RubricContext, step_id: str | None, level: InterventionLevel) -> str:
    step = next((s for s in context.steps if s.id == step_id), None)
    if step is None or level not in _LADDER or len(step.hints) <= _LADDER.index(level):
        return _GENERIC
    return step.hints[_LADDER.index(level)]


async def deliver(rt: SessionRuntime, decision: Decision, context: RubricContext) -> Intervention:
    """Record the intervention; show and speak it unless the session is in passive mode."""
    text = decision.draft
    if text is None or looks_like_code(text):
        if text is not None:
            logger.warning("leak guard replaced a draft in %s", rt.session.id)
            await rt.note("info", f"leak guard replaced the analyzer's wording for step {decision.step_id}")
        text = rubric_hint(context, decision.step_id, decision.level)
    config = rt.session.config
    intervention = Intervention(
        id=new_id(),
        t=rt.now_ms(),
        trigger=decision.trigger,
        level=decision.level,
        text=text,
        step_id=decision.step_id,
        speak=config.speak_replies,
        suppressed=config.feedback == FeedbackLevel.PASSIVE,
    )
    await rt.record(TimelineKind.INTERVENTION, intervention)
    if not intervention.suppressed:
        await rt.broadcast(InterviewerMessage(type="interviewer.message", intervention=intervention))
        # The replay's transcript shows what the interviewer said, alongside the candidate's turns.
        turn = TranscriptTurn(
            turn_id=new_id(),
            speaker="interviewer",
            text=text,
            start_ms=intervention.t,
            end_ms=intervention.t,
            final=True,
            source="text",
        )
        await rt.record(TimelineKind.TRANSCRIPT, turn)
    return intervention
