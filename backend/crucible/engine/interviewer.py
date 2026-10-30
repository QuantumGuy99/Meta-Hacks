"""Turns a policy decision into what the candidate sees and hears (PLAN §9.6).

The leak guard (code shape plus overlap with the reference), the analyzer's draft or a rubric hint or canned line,
delivery, `answer()` for the candidate's questions, `reply()` for the conversational lines (the warm-up), and
`say()` for lines a mode chooses.
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import math
import re
from functools import lru_cache
from typing import TYPE_CHECKING, Literal

from crucible.contracts.common import FeedbackLevel
from crucible.contracts.events import (
    Intervention,
    InterventionLevel,
    InterventionText,
    InterventionTrigger,
    TimelineKind,
    TranscriptTurn,
)
from crucible.contracts.ws import InterviewerMessage
from crucible.engine.context import RubricContext
from crucible.engine.ids import new_id
from crucible.engine.policy import LADDER_TRIGGERS, PASSIVE_DELIVERED, Decision
from crucible.engine.prompts import CANNED, PROMPTS

if TYPE_CHECKING:
    from crucible.engine.analyzer import StructuredModel
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


def leak_reason(text: str, reference: str | None = None) -> str | None:
    """Why `text` would hand over the answer, or None if it's safe to send (the full §9.6 leak guard).

    Code-shaped text is always rejected. With a `reference` (the reference solution, or a sample's fix), any
    line of `text` sharing ≥ 60% of the tokens of a non-trivial reference line is rejected too: that's the
    solution re-typed, whatever the wording around it.
    """
    if looks_like_code(text):
        return "it contains code"
    if reference:
        candidates = [_tokens(line) for line in text.splitlines() if line.strip()] + [_tokens(text)]
        for ref in _reference_lines(reference):
            if any(len(ref & c) / len(ref) >= OVERLAP_LIMIT for c in candidates):
                return "it repeats a line of the solution"
    return None


OVERLAP_LIMIT = 0.6
MIN_REFERENCE_TOKENS = 5  # shorter lines ("return best", "best = 0") are too generic to count as the solution
_TOKEN = re.compile(r"[a-z_][a-z0-9_]*|\d+|[^\sa-z0-9_]")


def _tokens(text: str) -> frozenset[str]:
    return frozenset(_TOKEN.findall(text.lower()))


@lru_cache(maxsize=64)
def _reference_lines(reference: str) -> tuple[frozenset[str], ...]:
    """Token sets of the reference's non-trivial lines: no signatures, comments, docstrings or short lines."""
    out = []
    for raw in reference.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "def ", "class ", '"""', "'''", "import ", "from ")):
            continue
        if len(_TOKEN.findall(line.lower())) >= MIN_REFERENCE_TOKENS:
            out.append(_tokens(line))
    return tuple(out)


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
    # ASKED lands here only when `answer()` had nothing usable: the canned Socratic line.
    line = CANNED.get(decision.trigger.value, _GENERIC)
    return line.format(minutes=max(1, math.ceil((remaining_s or 0) / 60)), line=decision.line)


async def deliver(rt: SessionRuntime, decision: Decision, context: RubricContext) -> Intervention:
    """Record the intervention; show it (and speak it, unless it's a note) when the policy didn't suppress it."""
    fallback = fallback_text(context, decision, remaining_s=rt.remaining_s())
    text = decision.draft if decision.draft is not None else fallback
    reason = leak_reason(text, context.reference_text)
    if reason is not None:
        logger.warning("leak guard replaced a %s message in %s: %s", decision.trigger, rt.session.id, reason)
        await rt.note(
            "info",
            f"leak guard replaced a {decision.trigger} message for step {decision.step_id}: {reason}",
        )
        safe = text != fallback and leak_reason(fallback, context.reference_text) is None
        text = fallback if safe else _GENERIC
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


ANSWER_DEADLINE_S = 15  # the wrapper's 6 s interviewer timeout (§21) plus its single retry
ANSWER_CONTEXT_MS = 180_000  # recent conversation shown with a question
ANSWER_CONTEXT_TURNS = 8


async def answer(
    rt: SessionRuntime, model: StructuredModel, context: RubricContext, question: str
) -> str | None:
    """Reply to a candidate's question (ASKED, §9.6) with the model, or None to use the canned line.

    The model sees only what the candidate can see (the problem statement, examples and constraints, their
    code and the recent conversation), never the rubric or the reference. Its reply goes through the leak guard;
    a rejected reply gets one retry asking for a Socratic question instead.
    """
    messages: list[dict[str, str]] = [
        {"role": "system", "content": PROMPTS["interviewer_answer"]},
        {"role": "user", "content": f"# Problem: {context.title}\n\n{context.brief_md}"},
        {"role": "user", "content": _session_state(rt, context, "Their question", question)},
    ]
    return await _spoken_line(
        rt,
        model,
        messages,
        "answer",
        "one short Socratic question",
        role="interviewer",
        reference=context.reference_text,
    )


ReplyKind = Literal["warmup", "warmup_close", "reply", "checkin", "probe"]
# What the warm-up reply ends with: a light follow-up, or nothing because the problem comes next (§3.1).
_WARMUP_ENDINGS: dict[ReplyKind, str] = {
    "warmup": "one light, friendly follow-up question about what they shared",
    "warmup_close": "no question: you're about to move on to the problem",
}


async def reply(
    rt: SessionRuntime,
    model: StructuredModel,
    kind: ReplyKind,
    said: str,
    context: RubricContext | None = None,
) -> str | None:
    """A short conversational line from the model (§9.6), or None so the caller uses its canned line.

    - `warmup`, `warmup_close`: a reaction to what the candidate shared about themselves; the model never sees
      the problem then.
    - `reply`: a reply to something the candidate said while solving (REPLY); `checkin`: a check-in after they've
      gone quiet (SILENT, IDLE); `probe`: a question that checks they understand the code they just wrote
      (PROBE). The model sees what the candidate sees (`context` is required), like `answer()`, never the rubric.
    Same leak guard and single retry as `answer()`.
    """
    if kind in _WARMUP_ENDINGS:
        user = json.dumps({"candidate_said": said, "end_with": _WARMUP_ENDINGS[kind]})
        messages = [
            {"role": "system", "content": PROMPTS["interviewer_warmup"]},
            {"role": "user", "content": user},
        ]
        return await _spoken_line(
            rt, model, messages, "warm-up reply", "one short, friendly sentence", role="conversation"
        )
    if context is None:
        raise ValueError(f"a {kind} needs the problem's context")
    last = {
        "reply": ("What they just said", said),
        "checkin": ("Now", "They've gone quiet for a while."),
        "probe": ("Now", "They've just finished a part of their solution."),
    }[kind]
    messages = [
        {"role": "system", "content": PROMPTS[f"interviewer_{kind}"]},
        {"role": "user", "content": f"# Problem: {context.title}\n\n{context.brief_md}"},
        {"role": "user", "content": _session_state(rt, context, *last)},
    ]
    return await _spoken_line(
        rt,
        model,
        messages,
        kind,
        "one short question about their thinking",
        role="conversation",
        reference=context.reference_text,
    )


async def _spoken_line(
    rt: SessionRuntime,
    model: StructuredModel,
    messages: list[dict[str, str]],
    what: str,
    instead: str,
    *,
    role: Literal["interviewer", "conversation"],
    reference: str | None = None,
) -> str | None:
    """One interviewer line from the model, through the leak guard. A rejected line gets one retry asking for
    `instead`; a failure or a second rejection is None, and the caller sends its canned line, never silence."""
    for _attempt in range(2):
        try:
            async with asyncio.timeout(ANSWER_DEADLINE_S):
                result = await model.complete_json(role, messages, InterventionText, session_id=rt.session.id)
        except Exception:  # task boundary: no line from the model means the canned one
            logger.exception("interviewer %s failed in %s", what, rt.session.id)
            await rt.note(
                "warning", f"the interviewer model didn't answer for the {what}; sent the canned line"
            )
            return None
        text = result.text.strip()
        reason = leak_reason(text, reference) if text else "it was empty"
        if reason is None:
            return text
        logger.warning("leak guard rejected the %s in %s: %s", what, rt.session.id, reason)
        await rt.note("info", f"leak guard rejected the interviewer's {what}: {reason}")
        retry = f"That reply was rejected because {reason}. Reply with {instead} instead."
        messages = [
            *messages,
            {"role": "assistant", "content": result.text},
            {"role": "user", "content": retry},
        ]
    return None


def _session_state(rt: SessionRuntime, context: RubricContext, heading: str, last: str) -> str:
    """What the candidate can see now (their code, the recent conversation), then `last` under `heading`."""
    main = context.files[0] if context.files else "solution.py"
    code = rt.code.code(main)
    numbered = "\n".join(f"{i:>3} | {line}" for i, line in enumerate(code.splitlines(), start=1)) or "(empty)"
    since = rt.now_ms() - ANSWER_CONTEXT_MS
    turns = [
        e.payload for e in rt.timeline.tail([TimelineKind.TRANSCRIPT], since_t=since) if e.payload["final"]
    ][-ANSWER_CONTEXT_TURNS:]
    conversation = "\n".join(f"- {t['speaker']}: {t['text']}" for t in turns) or "(nothing yet)"
    return (
        f"# Now\nPhase: {rt.session.phase}.\n\n## Their code ({main})\n```python\n{numbered}\n```\n\n"
        f"## Recent conversation\n{conversation}\n\n## {heading}\n{last}"
    )


async def say(
    rt: SessionRuntime,
    text: str,
    trigger: InterventionTrigger,
    level: InterventionLevel,
    *,
    speak: bool | None = None,
    step_id: str | None = None,
    fallback: str | None = None,
    reference: str | None = None,
) -> Intervention:
    """Say a line the caller chose (phase lines, grill questions) through the same leak guard (PLAN §9.6).

    `reference` is what the line must not repeat (a solution or fix). On a rejection it sends `fallback`, or
    the trigger's canned line. Shown in passive mode too: these lines run the interview, they aren't feedback.
    `speak` defaults to the session's "speak replies" setting.
    """
    reason = leak_reason(text, reference)
    if reason is not None:
        logger.warning("leak guard replaced a %s line in %s: %s", trigger, rt.session.id, reason)
        await rt.note("info", f"leak guard replaced a {trigger} line: {reason}")
        usable = fallback and leak_reason(fallback, reference) is None
        text = fallback if usable else CANNED.get(trigger.value, _GENERIC)
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
