"""Grill: the model says which expected points an answer hit; code computes the score (PLAN §11.5)."""

from __future__ import annotations

import ast
import asyncio
import json
import re
import uuid
from collections.abc import Sequence

from crucible.contracts.defense import Finding, GrillEval, GrillTurn
from crucible.contracts.events import InterventionText, TimelineKind
from crucible.defense.ports import EventSink, ModelClient, ModelUnavailable, note
from crucible.defense.prompts import PROMPTS

GRILL_EVAL_TIMEOUT_S = 20  # Spark medium took 4-15 s live (#22); at 10 s answers fell back to keywords
SAM_BONUS = 1
KEYWORD_HIT_RATIO = 0.4
# Keywords alone shouldn't fail a correct explanation on the root cause (#35): point 0 needs fewer words.
KEYWORD_ROOT_RATIO = 0.25
MAX_ANSWER_CHARS = 4_000  # about 3 minutes of speech; longer answers are cut before they reach the model
# The question waits on the plain-words rewrite (Spark low, about 1-3 s), so a slow one gives way to the audit's
# wording rather than leaving the candidate on a silent room.
PLAIN_TIMEOUT_S = 8
PLAIN_MAX_CHARS = 600  # about 90 words: a longer rewrite is rambling, and the audit's wording goes out
SAID_BEFORE_LINES = 6  # the interviewer's latest lines, so the next one doesn't repeat their phrasing
SAFE_FEEDBACK = "Think about what another request could be doing while this one waits. What could change?"
_STOPWORDS = frozenset(
    [
        "about",
        "after",
        "again",
        "against",
        "because",
        "before",
        "being",
        "between",
        "both",
        "could",
        "does",
        "doing",
        "during",
        "each",
        "from",
        "have",
        "having",
        "into",
        "itself",
        "just",
        "more",
        "most",
        "other",
        "over",
        "same",
        "should",
        "some",
        "such",
        "than",
        "that",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "under",
        "until",
        "very",
        "what",
        "when",
        "where",
        "which",
        "while",
        "will",
        "with",
        "would",
        "your",
    ]
)


def grill_question(finding: Finding, chaos_summary: str) -> str:
    """The question with the real numbers in front. (An LLM rewrite is P1; this is also its fallback.)"""
    return f"{chaos_summary}. {finding.grill.question}"


async def plain_question(
    finding: Finding,
    chaos_summary: str | None,
    question: str,
    llm: ModelClient,
    sink: EventSink,
    *,
    answer: str | None = None,
    reaction: str | None = None,
    said_before: Sequence[str] = (),
) -> str:
    """The grill question in everyday words (#88 item 6): for the first question, a sentence or two on what the
    attack did and what went wrong first; for a follow-up, a reaction to what they actually said, then the
    question (a smaller first step if they're lost). The model sees only what the candidate already has (the
    finding's title, file and category, the load test, the question, their answer and the grader's note, which
    never names the cause), plus the lines already said so it doesn't repeat them. Falls back to the audit's
    wording."""
    if chaos_summary:
        fallback = grill_question(finding, chaos_summary)
    else:
        fallback = f"{reaction} {question}" if reaction else question
    user = {
        "kind": "first" if chaos_summary else "follow_up",
        "finding": finding.model_dump(include={"title", "file", "category"}),
        "load_test": chaos_summary,
        "question": question,
        "their_answer": answer[:MAX_ANSWER_CHARS] if answer else None,
        "grader_note": reaction,
        "you_already_said": list(said_before)[-SAID_BEFORE_LINES:],
    }
    text = await _interviewer_line(llm, "grill_plain_system", user)
    if text is None:
        await note(sink, "info", f"Plain-words grill question for {finding.id} unavailable; audit wording.")
        return fallback
    return text


async def clarify(
    finding: Finding,
    chaos_summary: str,
    question: str,
    message: str,
    llm: ModelClient,
    *,
    said_before: Sequence[str] = (),
) -> str | None:
    """The interviewer's answer when the candidate asks something back during the grill ("what's p95?", "can you
    say that again?"), or None when the message is their answer (even one phrased as a question), which is then
    graded. Built from what the candidate already sees, so it can't give the cause away; on any failure the
    message is graded, as before."""
    user = {
        "finding": finding.model_dump(include={"title", "file", "category"}),
        "load_test": chaos_summary,
        "question_on_screen": question,
        "their_message": message[:MAX_ANSWER_CHARS],
        "you_already_said": list(said_before)[-SAID_BEFORE_LINES:],
    }
    return await _interviewer_line(llm, "grill_clarify_system", user)


async def _interviewer_line(llm: ModelClient, prompt: str, user: dict) -> str | None:
    """One spoken line from the `interviewer` role, or None when it's down, empty, too long or has code."""
    messages = [{"role": "system", "content": PROMPTS[prompt]}, {"role": "user", "content": json.dumps(user)}]
    try:
        out = await llm.complete_json("interviewer", messages, InterventionText, timeout_s=PLAIN_TIMEOUT_S)
    except ModelUnavailable:
        return None
    text = out.text.strip()
    if not text or len(text) > PLAIN_MAX_CHARS or looks_like_code(text):
        return None
    return text


def score_answer(
    n_points: int, ev: GrillEval, *, sam_node_id: str | None, finding_node_id: str | None
) -> tuple[int, bool]:
    """(score 0–10, root_cause_hit). Indexes the model invents are ignored. The SAM bonus never replaces
    the root cause: the verdict requires root_cause_hit separately."""
    if n_points <= 0:
        return 0, False
    hits = {i for i in ev.points_hit if 0 <= i < n_points}
    root_cause_hit = 0 in hits
    score = round(10 * len(hits) / n_points)
    if sam_node_id is not None and sam_node_id == finding_node_id:
        score = min(10, score + SAM_BONUS)
    return score, root_cause_hit


def agreed(a: GrillEval, b: GrillEval, n_points: int) -> GrillEval:
    """Code decides between two graders: a point counts when both marked it. A split on the root cause
    (point 0) asks the follow-up instead of failing the candidate outright: the second answer can settle it."""
    hit = sorted({i for i in a.points_hit if 0 <= i < n_points} & set(b.points_hit))
    split_on_root = (0 in a.points_hit) != (0 in b.points_hit)
    return GrillEval(
        points_hit=hit,
        points_missed=[i for i in range(n_points) if i not in hit],
        needs_follow_up=0 not in hit or split_on_root or a.needs_follow_up or b.needs_follow_up,
        feedback=a.feedback or b.feedback,
    )


def keyword_eval(points: list[str], answer: str) -> GrillEval:
    """Deterministic fallback when no model answers: a point is hit when ≥ 40% of its content words (by
    5-letter stem) appear in the answer (25% for point 0, the root cause). Cruder than the model; always
    logged as a fallback."""
    answer_stems = {w[:5] for w in _words(answer)}
    hit, missed = [], []
    for i, point in enumerate(points):
        stems = {w[:5] for w in _words(point)}
        ratio = len(stems & answer_stems) / len(stems) if stems else 0.0
        (hit if ratio >= (KEYWORD_ROOT_RATIO if i == 0 else KEYWORD_HIT_RATIO) else missed).append(i)
    return GrillEval(points_hit=hit, points_missed=missed, needs_follow_up=0 not in hit, feedback="")


async def evaluate_answer(
    finding: Finding, chaos_summary: str, answer: str, llm: ModelClient, sink: EventSink
) -> GrillEval:
    """Two Meta models grade in parallel (DEF-13, PLAN §11.11): Muse Spark (`grill_eval`) and a second model
    (`grill_check`). Code keeps only the points both marked. With one model down, the other grades alone;
    with both down, the keyword fallback grades."""
    messages = _messages(finding, chaos_summary, answer)
    primary, check = await asyncio.gather(
        _grade_with(llm, "grill_eval", messages), _grade_with(llm, "grill_check", messages)
    )
    if isinstance(primary, ModelUnavailable) and isinstance(check, ModelUnavailable):
        await note(
            sink,
            "warning",
            f"Grill grading models unavailable for {finding.id}; keyword fallback. ({primary})",
        )
        return keyword_eval(finding.grill.expected_points, answer)
    if isinstance(primary, ModelUnavailable) or isinstance(check, ModelUnavailable):
        down = "grill_eval" if isinstance(primary, ModelUnavailable) else "grill_check"
        await note(sink, "info", f"Grill for {finding.id} graded by one model ({down} unavailable).")
        ev = check if isinstance(primary, ModelUnavailable) else primary
    else:
        ev = agreed(primary, check, len(finding.grill.expected_points))
        if set(primary.points_hit) != set(check.points_hit):
            await note(sink, "info", f"Grill graders split on {finding.id}; only points both marked count.")
    if looks_like_code(ev.feedback):
        await note(sink, "warning", f"Grill feedback for {finding.id} contained code; replaced.")
        ev = ev.model_copy(update={"feedback": SAFE_FEEDBACK})
    return ev


async def _grade_with(llm: ModelClient, role: str, messages: list[dict]) -> GrillEval | ModelUnavailable:
    try:
        return await llm.complete_json(role, messages, GrillEval, timeout_s=GRILL_EVAL_TIMEOUT_S)
    except ModelUnavailable as exc:
        return exc


async def grade(
    finding: Finding,
    chaos_summary: str,
    answer: str,
    llm: ModelClient,
    sink: EventSink,
    *,
    sam_node_id: str | None = None,
    follow_up_asked: bool = False,
    earlier: GrillTurn | None = None,
) -> GrillTurn:
    """Grade one answer. With `earlier` (the follow-up case), points from both answers count together."""
    ev = await evaluate_answer(finding, chaos_summary, answer, llm, sink)
    turn_ids = [uuid.uuid4().hex[:12]]
    if earlier is not None:
        n = len(finding.grill.expected_points)
        hit = sorted(set(ev.points_hit) | set(earlier.eval.points_hit))
        ev = ev.model_copy(
            update={
                "points_hit": hit,
                "points_missed": [i for i in range(n) if i not in hit],
                "needs_follow_up": False,
            }
        )
        turn_ids = [*earlier.answer_turn_ids, *turn_ids]
    score, root = score_answer(
        len(finding.grill.expected_points), ev, sam_node_id=sam_node_id, finding_node_id=finding.node_id
    )
    turn = GrillTurn(
        finding_id=finding.id,
        question=grill_question(finding, chaos_summary),
        answer_turn_ids=turn_ids,
        follow_up_asked=follow_up_asked,
        eval=ev,
        sam_node_id=sam_node_id,
        root_cause_hit=root,
        score=score,
    )
    await sink.emit(TimelineKind.GRILL, turn)
    return turn


def looks_like_code(text: str) -> bool:
    """Minimal standalone leak check (SG's leak guard replaces it in the room): fences, defs, or ≥ 2 lines
    that parse as Python statements other than plain prose."""
    if "```" in text or re.search(r"\b(def|async def|class|import)\s+\w", text):
        return True
    code_lines = 0
    for line in text.splitlines():
        s = line.strip()
        if not s or (" " not in s and not s.endswith(")")):
            continue
        try:
            node = ast.parse(s)
        except SyntaxError:
            continue
        if node.body and not isinstance(node.body[0], ast.Expr):
            code_lines += 1
    return code_lines >= 2


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in _STOPWORDS]


def _messages(finding: Finding, chaos_summary: str, answer: str) -> list[dict]:
    user = {
        "finding": finding.model_dump(include={"title", "file", "line_start", "line_end", "explanation"}),
        "load_test": chaos_summary,
        "expected_points": dict(enumerate(finding.grill.expected_points)),
        "answer": answer[:MAX_ANSWER_CHARS],
    }
    return [
        {"role": "system", "content": PROMPTS["grill_eval_system"]},
        {"role": "user", "content": json.dumps(user)},
    ]
