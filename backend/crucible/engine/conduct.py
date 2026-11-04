"""Profanity in the candidate's words: a warning, a final warning, then the session ends.

Code decides, not a model: a word list matched on whole words (so "class" or "Scunthorpe" never count), with the
usual disguises (`f*ck`, `sh1t`). Each strike is a `system` note on the timeline, so the count survives a
reconnect, and the interviewer says each warning through the same path as its other lines.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from crucible.contracts.events import InterventionLevel, InterventionTrigger, TimelineKind
from crucible.contracts.ws import ErrorMsg

if TYPE_CHECKING:
    from crucible.engine.hub import SessionRuntime

STRIKES_TO_END = 3
WARNING = (
    "Please keep your language professional: profanity isn't acceptable in an interview. "
    "Repeated use will end this session."
)
FINAL_WARNING = (
    "This is your final warning. One more instance of profanity and the session will be terminated."
)
TERMINATED = "Session terminated due to profanity."
# The reason on the session's last phase change; the report page shows its banner from it.
TERMINATED_REASON = "terminated: profanity"
TERMINATED_CODE = "terminated_profanity"
STRIKE_NOTE = "conduct: profanity strike"

# Each stem allows the usual letter swaps; the edges are whole-word, with common endings.
_LETTER = {"a": "[a@4*]", "e": "[e3*]", "i": "[i1!*]", "o": "[o0*]", "u": "[u*v]", "s": "[s$5]"}
_STEMS = (
    "fuck",
    "fck",
    "fuk",
    "shit",
    "bitch",
    "cunt",
    "asshole",
    "bastard",
    "dick",
    "dickhead",
    "cock",
    "pussy",
    "motherfucker",
    "wanker",
    "twat",
    "slut",
    "whore",
    "retard",
    "faggot",
    "fag",
    "nigger",
    "nigga",
    "wtf",
    "stfu",
)
_ENDINGS = r"(?:s|es|er|ers|ed|ing|in|y|ty|head|face|hole)?"


def _stem(word: str) -> str:
    return "".join(f"{_LETTER.get(c, re.escape(c))}+" for c in word)


_PROFANITY = re.compile(
    rf"(?<![a-z0-9])(?:{'|'.join(_stem(w) for w in _STEMS)}){_ENDINGS}(?![a-z0-9])", re.IGNORECASE
)


def is_profane(text: str) -> bool:
    return _PROFANITY.search(text) is not None


def response(strike: int) -> tuple[str, bool]:
    """(what the interviewer says, whether the session ends) for the candidate's `strike`-th offence."""
    if strike >= STRIKES_TO_END:
        return TERMINATED, True
    return (FINAL_WARNING if strike == STRIKES_TO_END - 1 else WARNING), False


def strikes_so_far(rt: SessionRuntime) -> int:
    return sum(
        1
        for e in rt.timeline.tail([TimelineKind.SYSTEM])
        if e.payload.get("message", "").startswith(STRIKE_NOTE)
    )


async def answer_profanity(rt: SessionRuntime) -> None:
    """Record the strike, say the warning, and on the last strike end the session with the reason shown."""
    from crucible.engine.interviewer import say  # the interviewer imports the hub's types; keep this lazy

    strike = strikes_so_far(rt) + 1
    await rt.note("warning", f"{STRIKE_NOTE} {strike} of {STRIKES_TO_END}")
    text, ends = response(strike)
    # PHASE: a line that runs the interview, never "help" against the candidate's independence score.
    await say(rt, text, InterventionTrigger.PHASE, InterventionLevel.INFO)
    if ends:
        await rt.broadcast(ErrorMsg(type="error", code=TERMINATED_CODE, message=TERMINATED, retryable=False))
        await rt.end(TERMINATED_REASON)
