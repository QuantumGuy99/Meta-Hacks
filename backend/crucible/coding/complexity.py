"""Grading the wrap-up complexity answer for the coding report (COD-5, PLAN §10.5).

The model only writes down the bounds the candidate stated (`ComplexityClaim`); code decides whether they match an
acceptable approach in the rubric, comparing big-O expressions up to notation: `O(n·m log m)`, `O(nm log(m))` and
`O(m log m * n)` are the same bound.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import Counter
from collections.abc import Sequence
from typing import TYPE_CHECKING

from crucible.coding.prompts import COMPLEXITY_PROMPT
from crucible.contracts.coding import Approach, ComplexityClaim, ProblemSpec
from crucible.contracts.events import InterventionLevel, InterventionTrigger, TimelineEvent, TimelineKind
from crucible.engine.context import RubricContext

if TYPE_CHECKING:
    from crucible.engine.analyzer import StructuredModel

logger = logging.getLogger(__name__)

GRADE_DEADLINE_S = 20  # the registry's 8 s per attempt plus the wrapper's one retry; it runs at report time
# A bound as a sum of terms, each a sorted product of factors: O(n + r) → {(n,), (r,)}.
Bound = frozenset[tuple[str, ...]]

_WRAPPER = re.compile(r"^(?:big[\s-]*)?[oθ]\s*\((.*)\)$")
_TOKEN = re.compile(r"log|\^\d+|\d+(?:\.\d+)?|[a-z]|[()+]")
_SPELLING = str.maketrans({"²": "^2", "³": "^3", "·": " ", "×": " ", "⋅": " ", "*": " "})
# In case the model writes the word instead of the notation the prompt asks for.
_WORDS = {
    "linear": "n",
    "constant": "1",
    "quadratic": "n^2",
    "cubic": "n^3",
    "logarithmic": "log n",
    "time": "",
    "space": "",
}


def complexity_question(questions: Sequence[str]) -> int | None:
    """Which wrap-up question asks for the complexity (the first, in every rubric so far)."""
    return next((i for i, q in enumerate(questions) if "complexity" in q.lower()), None)


def complexity_answer(events: Sequence[TimelineEvent], index: int) -> str | None:
    """What the candidate said after wrap-up question `index`, before the next one was asked. Order is by `seq`:
    a typed answer and the next question are often recorded in the same millisecond. A spoken turn that started
    before the next question still belongs to this answer: it ends after the interviewer moved on."""
    asked = [
        e
        for e in events
        if e.kind == TimelineKind.INTERVENTION
        and e.payload["trigger"] == InterventionTrigger.PHASE
        and e.payload["level"] == InterventionLevel.QUESTION
    ]
    if index >= len(asked):
        return None
    question, following = asked[index], asked[index + 1] if index + 1 < len(asked) else None
    said = [
        e.payload["text"].strip()
        for e in sorted(events, key=lambda e: e.seq)
        if e.kind == TimelineKind.TRANSCRIPT
        and e.payload["speaker"] == "candidate"
        and e.payload["final"]
        and e.seq > question.seq
        and (following is None or e.seq < following.seq or e.payload["start_ms"] < following.t)
    ]
    return " ".join(s for s in said if s) or None


async def grade_complexity_answer(
    model: StructuredModel, spec: ProblemSpec, answer: str, *, session_id: str | None = None
) -> bool | None:
    """True if the stated bounds match an acceptable approach, False if not, None if the model call failed."""
    approaches = [{"name": a.name, "time": a.time, "space": a.space} for a in spec.rubric.approaches]
    problem = RubricContext.from_problem(spec).brief_md
    user = json.dumps({"problem": problem, "rubric_approaches": approaches, "answer": answer})
    messages = [{"role": "system", "content": COMPLEXITY_PROMPT}, {"role": "user", "content": user}]
    try:
        async with asyncio.timeout(GRADE_DEADLINE_S):
            claim = await model.complete_json("complexity", messages, ComplexityClaim, session_id=session_id)
    except Exception:  # task boundary: the report leaves the answer ungraded rather than guess
        logger.warning("complexity grading failed in %s", session_id, exc_info=True)
        return None
    return matches_acceptable(claim, spec.rubric.approaches)


def matches_acceptable(claim: ComplexityClaim, approaches: Sequence[Approach]) -> bool:
    """The stated time bound, and the space bound if they gave one, match the same acceptable approach.

    A missing space bound isn't held against them (a spoken answer can lose its tail to the next question); a
    missing or wrong time bound is.
    """
    if claim.time is None:
        return False
    return any(
        a.acceptable and covers(a.time, claim.time) and (claim.space is None or covers(a.space, claim.space))
        for a in approaches
    )


def covers(rubric: str, stated: str) -> bool:
    """The stated bound is the rubric's, or the rubric's with some added terms left out: O(n) for O(n + r), since
    candidates often drop a term the constraints keep small (r ≤ 50 in genre-sampler)."""
    r, s = canonical(rubric), canonical(stated)
    if r is None or s is None:
        return same_bound(rubric, stated)
    return bool(s) and s <= r


def same_bound(a: str, b: str) -> bool:
    """Equal up to notation; two bounds code can't read are compared as text without spaces."""
    ca, cb = canonical(a), canonical(b)
    if ca is None or cb is None:
        return _squash(a) == _squash(b)
    return ca == cb


def canonical(bound: str) -> Bound | None:
    """`O(n * m log m)` → {("log m", "m", "n")}, with constants and dominated terms dropped (`O(2n + 1)` is
    O(n)). None if it isn't a sum of products of single-letter variables, logs and powers."""
    text = bound.lower().translate(_SPELLING).replace("**", "^")
    text = re.sub(r"\blg\b|\blog_?\d+", "log", text).strip()
    text = re.sub(r"[a-z]{4,}", lambda m: _WORDS.get(m.group(), m.group()), text)
    wrapped = _WRAPPER.match(text)
    inner = wrapped.group(1) if wrapped else text
    tokens = _TOKEN.findall(inner)
    if not tokens or "".join(tokens) != re.sub(r"\s+", "", inner):
        return None  # empty, or something the tokenizer doesn't know, like a comma
    terms = _terms(tokens)
    return None if terms is None else _drop_dominated(terms)


# --- parsing -------------------------------------------------------------------------------------------------


def _terms(tokens: list[str]) -> list[tuple[str, ...]] | None:
    terms: list[tuple[str, ...]] = []
    factors: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == "+":
            terms.append(tuple(sorted(factors)))
            factors = []
            i += 1
            continue
        parsed = _factor(tokens, i)
        if parsed is None:
            return None
        found, i = parsed
        factors.extend(found)
    terms.append(tuple(sorted(factors)))
    return terms


def _factor(tokens: list[str], i: int) -> tuple[list[str], int] | None:
    """The factors starting at `tokens[i]` and the index after them; constants are dropped."""
    token = tokens[i]
    if token == "log":
        power, i = _power(tokens, i + 1)
        if i >= len(tokens):
            return None
        if tokens[i] == "(":
            group = _group(tokens, i)
            if group is None:
                return None
            inner, after = group
            name = inner[0] if len(inner) == 1 else f"({''.join(inner)})"
            return [f"log {name}"] * power, after
        if not tokens[i].isalpha() or tokens[i] == "log":
            return None
        return [f"log {tokens[i]}"] * power, i + 1
    if token.isalpha():
        power, after = _power(tokens, i + 1)
        return [token] * power, after
    if token[0].isdigit():
        _, after = _power(tokens, i + 1)
        return [], after
    if token == "(":
        group = _group(tokens, i)
        if group is None:
            return None
        inner, after = group
        power, after = _power(tokens, after)
        return list(inner) * power, after
    return None


def _group(tokens: list[str], i: int) -> tuple[tuple[str, ...], int] | None:
    """The single product inside the parenthesis at `tokens[i]`, and the index after it. A sum inside, like
    (n + m) * k, is beyond what rubrics write."""
    depth = 0
    for j in range(i, len(tokens)):
        depth += {"(": 1, ")": -1}.get(tokens[j], 0)
        if depth == 0:
            inner = _terms(tokens[i + 1 : j])
            return (inner[0], j + 1) if inner is not None and len(inner) == 1 else None
    return None


def _power(tokens: list[str], i: int) -> tuple[int, int]:
    if i < len(tokens) and tokens[i].startswith("^"):
        return int(tokens[i][1:]), i + 1
    return 1, i


def _drop_dominated(terms: list[tuple[str, ...]]) -> Bound:
    """Keep only terms no other term contains: n is inside n log n, and 1 inside everything."""
    unique = set(terms)
    counts = {t: Counter(t) for t in unique}
    return frozenset(t for t in unique if not any(o != t and counts[t] <= counts[o] for o in unique))


def _squash(bound: str) -> str:
    return re.sub(r"\s+", "", bound.lower())
