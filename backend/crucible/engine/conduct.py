"""Abusive language ends the interview on the spot, in both modes, as it would with a person (PLAN §9.1).

Code decides, not a model: a word list matched on whole words (so "class", "Scunthorpe" or "the update gets
lost" never count), with the usual disguises (`f*ck`, `sh1t`, `fuuuck`), plus insults or hostility aimed at the
interviewer and words speech-to-text bleeped. One offence is enough: the interviewer says so once, harshly, the
session ends, and the report is a fail (#93 warned twice first; Srinithin asked for the real-interview rule).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from crucible.contracts.events import IntegrityFlag, InterventionLevel, InterventionTrigger, TimelineKind
from crucible.contracts.report import Report
from crucible.contracts.ws import ErrorMsg
from crucible.engine.ids import new_id

if TYPE_CHECKING:
    from crucible.engine.hub import SessionRuntime

TERMINATED = "Interview ended: abusive language."
# The reason on the session's last phase change; the report page shows its banner from it (ReportView.tsx).
TERMINATED_REASON = "terminated: abusive language"
TERMINATED_CODE = "terminated_conduct"
CONDUCT_NOTE = "conduct: abusive language, the interview was ended"
FLAG_DETAIL = "Used abusive language toward the interviewer, so the interview was ended."
SUMMARY = (
    "The interview was ended early because the candidate used abusive language toward the interviewer. In a "
    "real interview that ends the process on the spot, whatever the technical work, so this one is a fail."
)
IMPROVEMENT = "Stay professional under pressure: frustration is fine to say, insults and profanity are not."

# Each stem allows the usual letter swaps; the edges are whole-word, with common endings.
_LETTER = {"a": "[a@4*]", "e": "[e3*]", "i": "[i1!*]", "o": "[o0*]", "u": "[u*v]", "s": "[s$5]"}
_STEMS = (
    "fuck",
    "fck",
    "fuk",
    "shit",
    "bullshit",
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


_PROFANITY = rf"(?<![a-z0-9])(?:{'|'.join(_stem(w) for w in _STEMS)}){_ENDINGS}(?![a-z0-9])"
# Insults aimed at the interviewer: "you idiot", "you're so useless", "this interview is garbage". Only straight
# at them: "you know, this approach is dumb" is the candidate judging their own work.
_INSULT = r"idiot\w*|moron\w*|stupid|dumb|useless|pathetic|worthless|trash|garbage|loser|clown|incompetent"
_INTENSIFIER = r"so|such|a|an|really|completely|totally|absolutely|absolute|the most|an absolute"
_AT_YOU = rf"\b(?:you(?:'?re| are)?|u r|ur)\s+(?:(?:{_INTENSIFIER})\s+)*(?:{_INSULT})\b"
_AT_THIS = rf"\b(?:this|the)\s+(?:interview|question|interviewer)\s+(?:is\s+)?(?:\w+\s+)?(?:{_INSULT})\b"
_HOSTILE = r"\b(?:shut up|screw you|go to hell|kys|kill yourself|piss off|eat sh\w*)\b"
# Speech-to-text may bleep a word ("[ __ ]", "f***") rather than spell it.
_BLEEP = r"\[\s*_{2,}\s*\]|\bf\*{2,}"
_ABUSE = re.compile(rf"{_PROFANITY}|{_AT_YOU}|{_AT_THIS}|{_HOSTILE}|{_BLEEP}", re.IGNORECASE)


def crossed_line(text: str) -> bool:
    """Whether what the candidate said or typed is abusive enough to end the interview."""
    return _ABUSE.search(text) is not None


async def end_for_conduct(rt: SessionRuntime) -> None:
    """A note and a flag for the report, one harsh line, an error the room shows, and the interview is over."""
    from crucible.engine.interviewer import say  # the interviewer imports the hub's types; keep this lazy
    from crucible.engine.prompts import CANNED

    await rt.note("warning", CONDUCT_NOTE)
    flag = IntegrityFlag(
        id=new_id(), t=rt.now_ms(), kind="conduct", detail=FLAG_DETAIL, chars=None, duration_ms=None
    )
    await rt.record(TimelineKind.INTEGRITY, flag, t=flag.t)
    await say(rt, CANNED["conduct"], InterventionTrigger.CONDUCT, InterventionLevel.NUDGE)
    await rt.broadcast(ErrorMsg(type="error", code=TERMINATED_CODE, message=TERMINATED, retryable=False))
    await rt.end(TERMINATED_REASON)


def failed_for_conduct(report: Report) -> Report:
    """The report of an interview ended for abusive language: an overall 0, a plain summary, a failed verdict."""
    defense = report.defense
    if defense is not None:
        reasons = ["Ended early for abusive language toward the interviewer.", *defense.verdict.reasons]
        defense = defense.model_copy(
            update={"verdict": defense.verdict.model_copy(update={"passed": False, "reasons": reasons})}
        )
    return report.model_copy(
        update={
            "overall": 0,
            "summary": SUMMARY,
            "strengths": [],
            "improvements": [IMPROVEMENT, *report.improvements][:3],
            "defense": defense,
        }
    )
