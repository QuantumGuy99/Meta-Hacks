"""The "Ask Crucible" guide (#25): Muse Spark suggests a reply and one app action; code decides what is shown.

The model only ever sees the question, the page name and public facts about the app, so there is nothing
secret it could leak. Code still drops actions during a live session, checks every action against what
exists, and runs every reply through the interviewer's leak guard.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Protocol, TypeVar

from pydantic import BaseModel

from crucible.contracts.guide import GuideAction, GuideAsk, GuideDraft, GuideReply
from crucible.engine.interviewer import leak_reason
from crucible.guide.prompts import PROMPTS

logger = logging.getLogger(__name__)

GUIDE_TIMEOUT_S = 8
MAX_REPLY_CHARS = 600
NO_ACTION = GuideAction(kind="none", page=None, difficulty=None, project_id=None)
SAFE_REPLY = "I can only help you find your way around Crucible. What would you like to do?"
IN_SESSION_REPLY = (
    "You're in a live interview, so I'll stay out of the way. Ask the interviewer if you're stuck."
)

T = TypeVar("T", bound=BaseModel)


class GuideModelUnavailable(Exception):
    """No model answered; the guide uses its rule-based reply."""


class GuideModel(Protocol):
    async def complete_json(
        self, role: str, messages: list[dict], schema: type[T], *, timeout_s: float
    ) -> T: ...


async def ask(body: GuideAsk, model: GuideModel | None, samples: set[str]) -> GuideReply:
    """Ask the model, then decide in code; any model failure gets the rule-based reply."""
    if model is None:
        return fallback_reply(body)
    try:
        draft = await model.complete_json("guide", messages(body), GuideDraft, timeout_s=GUIDE_TIMEOUT_S)
    except GuideModelUnavailable as exc:
        logger.warning("guide model unavailable, rule-based reply: %s", exc)
        return fallback_reply(body)
    return decide(draft, body, samples)


def decide(draft: GuideDraft, body: GuideAsk, samples: set[str]) -> GuideReply:
    """Code decides: no actions in a live session, only actions that exist, and a reply that can't leak."""
    reply = draft.reply.strip()[:MAX_REPLY_CHARS] or SAFE_REPLY
    if reason := leak_reason(reply):
        logger.warning("guide reply replaced: %s", reason)
        reply = SAFE_REPLY
    action = NO_ACTION if body.in_session else allowed_action(draft.action, samples)
    return GuideReply(reply=reply, action=action, source="model")


def allowed_action(action: GuideAction, samples: set[str]) -> GuideAction:
    """Keep only the fields each kind uses; an unknown sample becomes "open the Defense picker"."""
    match action.kind:
        case "open_page" if action.page is not None:
            return GuideAction(kind="open_page", page=action.page, difficulty=None, project_id=None)
        case "start_coding" if action.difficulty is not None:
            return GuideAction(kind="start_coding", page=None, difficulty=action.difficulty, project_id=None)
        case "start_defense" if action.project_id in samples:
            return GuideAction(kind="start_defense", page=None, difficulty=None, project_id=action.project_id)
        case "start_defense":
            return GuideAction(kind="open_page", page="defense", difficulty=None, project_id=None)
        case _:
            return NO_ACTION


def fallback_reply(body: GuideAsk) -> GuideReply:
    """No model: point to the right page from keywords, or explain the two modes."""
    if body.in_session:
        return GuideReply(reply=IN_SESSION_REPLY, action=NO_ACTION, source="fallback")
    q = body.question.lower()
    if re.search(r"\b(defen[cs]e|project|chaos|load|break|merge gate)\b", q):
        reply = "Project Defense breaks a sample app under load, then you explain and fix it. Opening it now."
        return GuideReply(reply=reply, action=_open("defense"), source="fallback")
    if re.search(r"\b(coding|interview|problem|leetcode|practi[cs]e)\b", q):
        reply = "The Live Coding Interview gives you a problem and watches how you solve it. Opening it now."
        return GuideReply(reply=reply, action=_open("coding"), source="fallback")
    if re.search(r"\b(report|replay|score|feedback)\b", q):
        reply = "Your report has your scores and a replay of the session. Opening it now."
        return GuideReply(reply=reply, action=_open("report"), source="fallback")
    reply = (
        "Crucible has two modes: a Live Coding Interview, and Project Defense, where your code is broken under "
        "load and you defend the fix. Which would you like?"
    )
    return GuideReply(reply=reply, action=NO_ACTION, source="fallback")


def messages(body: GuideAsk) -> list[dict]:
    history = [{"role": "user" if t.role == "user" else "assistant", "content": t.text} for t in body.history]
    context = {"page": body.page, "in_session": body.in_session, "question": body.question}
    return [
        {"role": "system", "content": PROMPTS["guide_system"]},
        *history,
        {"role": "user", "content": json.dumps(context)},
    ]


def _open(page: str) -> GuideAction:
    return GuideAction(kind="open_page", page=page, difficulty=None, project_id=None)
