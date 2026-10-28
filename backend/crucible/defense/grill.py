"""Grill: the model says which expected points an answer hit; code computes the score (PLAN §11.5)."""

from __future__ import annotations

import ast
import json
import re
import uuid

from crucible.contracts.defense import Finding, GrillEval, GrillTurn
from crucible.contracts.events import TimelineKind
from crucible.defense.ports import EventSink, ModelClient, ModelUnavailable, note
from crucible.defense.prompts import PROMPTS

GRILL_EVAL_TIMEOUT_S = 20  # Spark medium took 4-15 s live (#22); at 10 s answers fell back to keywords
SAM_BONUS = 1
KEYWORD_HIT_RATIO = 0.4
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


def keyword_eval(points: list[str], answer: str) -> GrillEval:
    """Deterministic fallback when no model answers: a point is hit when ≥ 40% of its content words (by
    5-letter stem) appear in the answer. Cruder than the model; always logged as a fallback."""
    answer_stems = {w[:5] for w in _words(answer)}
    hit, missed = [], []
    for i, point in enumerate(points):
        stems = {w[:5] for w in _words(point)}
        ratio = len(stems & answer_stems) / len(stems) if stems else 0.0
        (hit if ratio >= KEYWORD_HIT_RATIO else missed).append(i)
    return GrillEval(points_hit=hit, points_missed=missed, needs_follow_up=0 not in hit, feedback="")


async def evaluate_answer(
    finding: Finding, chaos_summary: str, answer: str, llm: ModelClient, sink: EventSink
) -> GrillEval:
    try:
        ev = await llm.complete_json(
            "grill_eval", _messages(finding, chaos_summary, answer), GrillEval, timeout_s=GRILL_EVAL_TIMEOUT_S
        )
    except ModelUnavailable as exc:
        await note(
            sink, "warning", f"Grill grading model unavailable for {finding.id}; keyword fallback. ({exc})"
        )
        return keyword_eval(finding.grill.expected_points, answer)
    if looks_like_code(ev.feedback):
        await note(sink, "warning", f"Grill feedback for {finding.id} contained code; replaced.")
        ev = ev.model_copy(update={"feedback": SAFE_FEEDBACK})
    return ev


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
        "answer": answer,
    }
    return [
        {"role": "system", "content": PROMPTS["grill_eval_system"]},
        {"role": "user", "content": json.dumps(user)},
    ]
