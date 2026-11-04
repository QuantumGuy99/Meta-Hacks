"""Abusive language ends the interview on the spot, as it would with a person (PLAN §9.1, both modes).

Code decides, from a fixed list: profanity, slurs, and insults or hostility aimed at the interviewer. A model
isn't asked, so the check is instant and the same every time.
"""

from __future__ import annotations

import re

from crucible.contracts.report import Report

# Whole words only: "class", "assess", "Dickens" and "shiitake" stay clean. No everyday phrases that technical
# answers use ("the update gets lost", "kill the process", "fire retardant").
_PROFANITY = (
    r"f+u+c+k\w*|f[*#@]+k\w*|motherf\w*|wtf|stfu|"
    r"sh[i1]t\w*|bullsh[i1]t\w*|s[*]{2,}t|"
    r"b[i1]tch\w*|bastard\w*|assholes?|a[*]+hole|dumbass\w*|jackass\w*|"
    r"cunt\w*|dickheads?|douche\w*|prick|twat\w*|wanker\w*|"
    r"retard(?:ed|s)?|n[i1]gg\w*|faggot\w*|fags?"
)
# Insults aimed at the interviewer: "you idiot", "you're so useless", "this interview is garbage". Only straight
# at them: "you know, this approach is dumb" is the candidate judging their own work.
_INSULT = r"idiot\w*|moron\w*|stupid|dumb|useless|pathetic|worthless|trash|garbage|loser|clown|incompetent"
_INTENSIFIER = r"so|such|a|an|really|completely|totally|absolutely|absolute|the most|an absolute"
_AT_YOU = rf"\b(?:you(?:'?re| are)?|u r|ur)\s+(?:(?:{_INTENSIFIER})\s+)*(?:{_INSULT})\b"
_AT_THIS = rf"\b(?:this|the)\s+(?:interview|question|interviewer)\s+(?:is\s+)?(?:\w+\s+)?(?:{_INSULT})\b"
_HOSTILE = r"\b(?:shut up|screw you|go to hell|kys|kill yourself|piss off|eat sh\w*)\b"
# Speech-to-text may bleep a word ("[ __ ]", "f***") rather than spell it.
_BLEEP = r"\[\s*_{2,}\s*\]|\bf\*{2,}"
_ABUSE = re.compile(rf"\b(?:{_PROFANITY})\b|{_AT_YOU}|{_AT_THIS}|{_HOSTILE}|{_BLEEP}", re.IGNORECASE)

SUMMARY = (
    "The interview was ended early because the candidate used abusive language toward the interviewer. In a "
    "real interview that ends the process on the spot, whatever the technical work, so this one is a fail."
)
IMPROVEMENT = "Stay professional under pressure: frustration is fine to say, insults and profanity are not."


def crossed_line(text: str) -> bool:
    """Whether what the candidate said or typed is abusive enough to end the interview."""
    return bool(_ABUSE.search(text))


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
