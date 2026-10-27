"""Turns a policy decision into what the candidate sees and hears (PLAN §9.6).

So far: the code check of the leak guard, the analyzer's draft or a rubric hint or canned line, delivery, and
`say()` for lines a mode chooses. ENG-6 adds phrasing, answers to questions and the reference-overlap check.
"""

from __future__ import annotations

import ast
import logging
import math
from typing import TYPE_CHECKING

from crucible.contracts.common import FeedbackLevel
from crucible.contracts.events import (
    Intervention,
    InterventionLevel,
    InterventionTrigger,
    TimelineKind,
    TranscriptTurn,
)
from crucible.contracts.ws import InterviewerMessage
from crucible.engine.context import RubricContext
from crucible.engine.ids import new_id
from crucible.engine.policy import LADDER_TRIGGERS, PASSIVE_DELIVERED, Decision
from crucible.engine.prompts import CANNED

if TYPE_CHECKING:
    from crucible.engine.hub import SessionRuntime

logger = logging.getLogger(__name__)

_LADDER = [InterventionLevel.NUDGE, InterventionLevel.QUESTION, InterventionLevel.HINT]
_GENERIC = "Take a step back and walk me through what you're doing."
TEXT_ONLY = frozenset({InterventionTrigger.PASTE, InterventionTrigger.TIME_WARNING})  # notes, not speech


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


def fallback_text(context: RubricContext, decision: Decision, *, remaining_s: int | None) -> str:
    """The text without a usable draft: the rubric hint for a ladder rule, else the trigger's canned line."""
    if decision.level == InterventionLevel.CONCEPT:
        return CANNED["concept"]
    if decision.trigger in LADDER_TRIGGERS and decision.step_id is not None:
        return rubric_hint(context, decision.step_id, decision.level)
    # TODO(ENG-6): Interviewer.answer() replies to ASKED; until then it gets the canned Socratic line.
    line = CANNED.get(decision.trigger.value, _GENERIC)
    return line.format(minutes=max(1, math.ceil((remaining_s or 0) / 60)), line=decision.line)


async def deliver(rt: SessionRuntime, decision: Decision, context: RubricContext) -> Intervention:
    """Record the intervention; show it (and speak it, unless it's a note) when the policy didn't suppress it."""
    fallback = fallback_text(context, decision, remaining_s=rt.remaining_s())
    text = decision.draft if decision.draft is not None else fallback
    if looks_like_code(text):
        logger.warning("leak guard replaced a %s message in %s", decision.trigger, rt.session.id)
        await rt.note(
            "info",
            f"leak guard replaced the wording of a {decision.trigger} message for step {decision.step_id}",
        )
        text = _GENERIC if text == fallback or looks_like_code(fallback) else fallback
    config = rt.session.config
    # The policy suppresses in passive mode; this keeps any other caller from showing unsolicited text there.
    passive = config.feedback == FeedbackLevel.PASSIVE and decision.trigger not in PASSIVE_DELIVERED
    intervention = Intervention(
        id=new_id(),
        t=rt.now_ms(),
        trigger=decision.trigger,
        level=decision.level,
        text=text,
        step_id=decision.step_id,
        speak=config.speak_replies and decision.trigger not in TEXT_ONLY,
        suppressed=decision.suppressed or passive,
    )
    await _record_and_show(rt, intervention)
    return intervention


async def say(
    rt: SessionRuntime,
    text: str,
    trigger: InterventionTrigger,
    level: InterventionLevel,
    *,
    speak: bool | None = None,
    step_id: str | None = None,
    fallback: str | None = None,
) -> Intervention:
    """Say a line the caller chose (phase lines, grill questions) through the same leak guard (PLAN §9.6).

    On a rejection it sends `fallback`, or the trigger's canned line. Shown in passive mode too: these lines run
    the interview, they aren't feedback. `speak` defaults to the session's "speak replies" setting.
    """
    if looks_like_code(text):
        logger.warning("leak guard replaced a %s line in %s", trigger, rt.session.id)
        await rt.note("info", f"leak guard replaced the wording of a {trigger} line")
        text = fallback if fallback and not looks_like_code(fallback) else CANNED.get(trigger.value, _GENERIC)
    intervention = Intervention(
        id=new_id(),
        t=rt.now_ms(),
        trigger=trigger,
        level=level,
        text=text,
        step_id=step_id,
        speak=rt.session.config.speak_replies if speak is None else speak,
        suppressed=False,
    )
    await _record_and_show(rt, intervention)
    return intervention


async def _record_and_show(rt: SessionRuntime, intervention: Intervention) -> None:
    await rt.record(TimelineKind.INTERVENTION, intervention)
    if not intervention.suppressed:
        await rt.broadcast(InterviewerMessage(type="interviewer.message", intervention=intervention))
        # The replay's transcript shows what the interviewer said, alongside the candidate's turns.
        turn = TranscriptTurn(
            turn_id=new_id(),
            speaker="interviewer",
            text=intervention.text,
            start_ms=intervention.t,
            end_ms=intervention.t,
            final=True,
            source="text",
        )
        await rt.record(TimelineKind.TRANSCRIPT, turn)
