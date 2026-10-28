"""ReportBuilder: the end-of-session report for both modes (PLAN §9.8).

Code computes the metrics and picks the candidate moments; the `report` model (Wonder, then Spark) words a
draft; code merges the two, deciding every score it can measure. When no model answers, a metrics-only template
report is built instead, so every ended session gets a report.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from typing import TYPE_CHECKING

from pydantic import BaseModel

from crucible.contracts.coding import Analysis, StepStatus
from crucible.contracts.common import Mode, Phase
from crucible.contracts.defense import AuditResult, ChaosRun, GrillTurn, Verdict
from crucible.contracts.events import (
    EditorEvent,
    IntegrityFlag,
    Intervention,
    InterventionLevel,
    InterventionTrigger,
    PhaseChange,
    RunResult,
    TimelineEvent,
    TimelineKind,
    TranscriptTurn,
)
from crucible.contracts.report import (
    CandidateMoment,
    CodingExtra,
    DefenseExtra,
    DimensionScore,
    Metrics,
    Moment,
    MomentKind,
    Report,
    ReportDraft,
)
from crucible.engine.analyzer import Analyzer
from crucible.engine.prompts import PROMPTS

if TYPE_CHECKING:
    from crucible.engine.analyzer import StructuredModel
    from crucible.engine.context import RubricContext
    from crucible.engine.hub import SessionRuntime

logger = logging.getLogger(__name__)

REPORT_DEADLINE_S = 100  # Wonder's 45 s (§21), then Spark's 45 s, with margin; then the template
TEMPLATE_MODEL = "template"
MAX_MOMENTS = 14
LONG_SILENCE_MS = 60_000  # a quieter stretch than this becomes a moment
HINT_LEVELS = (
    InterventionLevel.NUDGE,
    InterventionLevel.QUESTION,
    InterventionLevel.HINT,
    InterventionLevel.CONCEPT,
)
# Interventions that aren't help: phase lines, the warm-up and grill questions run the interview; paste and time
# notes are reminders. They don't count as interventions shown, nor against independence.
NOT_HELP = frozenset(
    {
        InterventionTrigger.PHASE,
        InterventionTrigger.WARMUP,
        InterventionTrigger.GRILL,
        InterventionTrigger.PASTE,
        InterventionTrigger.TIME_WARNING,
    }
)
# Phases where the candidate is expected to talk, type or run; silence elsewhere is the product working.
CANDIDATE_PHASES = frozenset({Phase.CLARIFY, Phase.CODING, Phase.WRAP_UP, Phase.GRILL, Phase.FIX})
TYPING = frozenset({"change", "paste", "undo", "redo"})
DIMENSIONS: dict[Mode, tuple[str, ...]] = {
    Mode.CODING: (
        "problem_solving",
        "correctness",
        "code_quality",
        "communication",
        "independence",
        "debugging",
    ),
    Mode.DEFENSE: ("system_understanding", "debugging", "correctness", "communication", "independence"),
}
# Independence in the template report: each shown hint costs more the more it gave away (§9.8).
HINT_COST = {"nudge": 1.0, "question": 1.5, "hint": 2.5, "concept": 4.0}
MAX_TURNS = 80
MAX_TURN_CHARS = 300
MAX_CODE_CHARS = 12_000


@dataclass(frozen=True, slots=True)
class Pick:
    """A candidate moment chosen by code. `rank` decides which survive when there are too many."""

    t: int
    kind: MomentKind
    title: str
    facts: str
    rank: int


# --- the async shell ---------------------------------------------------------------------------------------


async def build_report(rt: SessionRuntime, model: StructuredModel | None) -> Report:
    """Build the report from the stored timeline; any model failure falls back to the template report."""
    if model is not None:
        await final_analysis(rt, model)
    events = await rt.timeline.read()
    end_ms = ended_at_ms(events, default=rt.now_ms())
    extra = await rt.controller.report_extra(rt)
    context = rt.last_context
    metrics = compute_metrics(events, end_ms)
    picks = pick_moments(events, end_ms, step_titles(context))
    draft, model_name = None, TEMPLATE_MODEL
    if model is None:
        await rt.note("warning", "no report model is configured; built a metrics-only report")
    else:
        messages = draft_messages(rt, events, end_ms, metrics, picks, extra, context)
        try:
            async with asyncio.timeout(REPORT_DEADLINE_S):
                draft, model_name = await model.complete_json_with_model(
                    "report", messages, ReportDraft, session_id=rt.session.id
                )
        except Exception:  # task boundary: the template report is the fallback, never no report
            logger.exception("report model failed for %s", rt.session.id)
            await rt.note("warning", "the report model didn't answer; built a metrics-only report")
    mode = rt.session.config.mode
    if draft is None:
        draft = template_draft(metrics, picks, extra, events)
    return merge(rt.session.id, mode, draft, metrics, picks, extra, model_name, rt.wall_now())


async def final_analysis(rt: SessionRuntime, model: StructuredModel) -> None:
    """Analyze the final code once if it changed since the last analysis, so the step statuses in the report
    match it. The live analyzer stops when the engine detaches, often right after the passing submit."""
    context = rt.last_context
    if context is None or not rt.code.changed_since_analysis():
        return
    analyzer = Analyzer(rt, context, model, _ignore_analysis)
    earlier = rt.timeline.tail([TimelineKind.ANALYSIS])
    if earlier:
        analyzer.previous = Analysis.model_validate(earlier[-1].payload)
    await analyzer.run("final")  # a failure leaves a note; the report uses the earlier statuses


async def _ignore_analysis(analysis: Analysis) -> None:
    return None  # the session is over: no notes panel or policy to update


# --- metrics (§7.5: computed in code, never by the LLM) ----------------------------------------------------


def compute_metrics(events: Sequence[TimelineEvent], end_ms: int) -> Metrics:
    runs = payloads(events, TimelineKind.RUN, RunResult)
    edits = payloads(events, TimelineKind.EDITOR, EditorEvent)
    shown = help_shown(events)
    submits = [r for r in runs if r.kind == "submit"]
    hidden = [c for c in submits[-1].cases if not c.visible] if submits else []
    first_edit = next((e.t for e in edits if e.kind in TYPING), None)
    turns = [t for t in payloads(events, TimelineKind.TRANSCRIPT, TranscriptTurn) if t.speaker == "candidate"]
    silence_ms, _ = longest_silence(events, end_ms)
    return Metrics(
        duration_s=end_ms // 1000,
        time_to_first_edit_s=None if first_edit is None else first_edit // 1000,
        time_to_first_run_s=runs[0].t // 1000 if runs else None,
        runs=sum(r.kind == "run" for r in runs),
        submits=len(submits),
        hidden_passed=sum(c.passed for c in hidden) if hidden else None,
        hidden_total=len(hidden) if hidden else None,
        interventions_shown=len(shown),
        hints_by_level={level.value: sum(i.level == level for i in shown) for level in HINT_LEVELS},
        chars_typed=sum(len(c.text) for e in edits if e.kind == "change" for c in e.changes),
        chars_pasted=sum(_pasted(e) for e in edits if e.kind == "paste"),
        tab_hidden_s=_hidden_ms(edits, end_ms) // 1000,
        talk_time_s=sum(t.end_ms - t.start_ms for t in turns if t.final and t.source == "voice") // 1000,
        longest_silence_s=silence_ms // 1000,
    )


def longest_silence(events: Sequence[TimelineEvent], end_ms: int) -> tuple[int, int]:
    """The longest stretch (ms, and when it started) in a candidate phase with no talking, typing or runs."""
    activity: list[int] = []
    for e in events:
        if (e.kind == TimelineKind.EDITOR and e.payload["kind"] in TYPING) or e.kind == TimelineKind.RUN:
            activity.append(e.t)
        elif e.kind == TimelineKind.TRANSCRIPT and e.payload["speaker"] == "candidate":
            activity += [e.payload["start_ms"], e.payload["end_ms"]]  # speaking isn't silence
    activity.sort()
    best = (0, 0)
    for start, stop in _phase_spans(events, end_ms, CANDIDATE_PHASES):
        marks = [start, *(t for t in activity if start < t < stop), stop]
        for a, b in pairwise(marks):
            if b - a > best[0]:  # ties keep the earliest
                best = (b - a, a)
    return best


def ended_at_ms(events: Sequence[TimelineEvent], *, default: int) -> int:
    ends = [e.t for e in events if e.kind == TimelineKind.PHASE and e.payload["to_phase"] == Phase.ENDED]
    return ends[-1] if ends else default


def help_shown(events: Sequence[TimelineEvent]) -> list[Intervention]:
    """Interventions the candidate saw that helped them (not phase lines, grill questions or notes)."""
    return [
        i
        for i in payloads(events, TimelineKind.INTERVENTION, Intervention)
        if not i.suppressed and i.trigger not in NOT_HELP
    ]


# --- candidate moments (§9.8: selected by code, worded by the LLM) -------------------------------------------


def pick_moments(events: Sequence[TimelineEvent], end_ms: int, steps: Mapping[str, str]) -> list[Pick]:
    """8–14 moments for the report (fewer in a short session), sorted by time."""
    picks = [
        *_coding_picks(events),
        *_help_picks(events, steps),
        *_integrity_picks(events),
        *_wrap_up_picks(events),
        *_defense_picks(events),
    ]
    silence_ms, silence_t = longest_silence(events, end_ms)
    if silence_ms >= LONG_SILENCE_MS:
        facts = f"No talking, typing or runs for {silence_ms // 1000} s from {clock(silence_t)}."
        picks.append(Pick(silence_t, "issue", "Longest silence", facts, 4))
    kept = sorted(picks, key=lambda p: (p.rank, p.t))[:MAX_MOMENTS]
    return sorted(kept, key=lambda p: p.t)


def _coding_picks(events: Sequence[TimelineEvent]) -> list[Pick]:
    picks: list[Pick] = []
    edit = next(
        (e for e in events if e.kind == TimelineKind.EDITOR and e.payload["kind"] in TYPING),
        None,
    )
    if edit is not None:
        picks.append(Pick(edit.t, "milestone", "Started coding", f"First edit at {clock(edit.t)}.", 1))
    plan = next(
        ((e.t, a) for e, a in _analyses(events) if a.stated_plan),
        None,
    )
    if plan is not None:
        picks.append(Pick(plan[0], "good", "Stated a plan", f"Plan stated: {plan[1].stated_plan}", 2))
    runs = payloads(events, TimelineKind.RUN, RunResult)
    submits = [r for r in runs if r.kind == "submit"]
    passing = next((r for r in runs if r.total and r.passed == r.total), None)
    # When the first passing run is the final submit, the "Submitted" moment already says so.
    if passing is not None and not (submits and passing.run_id == submits[-1].run_id):
        facts = f"First {passing.kind} with every test passing ({passing.total} tests) at {clock(passing.t)}."
        picks.append(Pick(passing.t, "good", "First passing run", facts, 2))
    if submits:
        last = submits[-1]
        kind: MomentKind = "good" if last.total and last.passed == last.total else "issue"
        facts = f"Final submit: {last.passed} of {last.total} tests passed" + (
            " (timed out)." if last.timed_out else "."
        )
        picks.append(Pick(last.t, kind, "Submitted", facts, 1))
    return picks


def _help_picks(events: Sequence[TimelineEvent], steps: Mapping[str, str]) -> list[Pick]:
    picks: list[Pick] = []
    for i in help_shown(events):
        if i.trigger == InterventionTrigger.ASKED:
            facts = f'The candidate asked a question; the interviewer replied: "{i.text}"'
            picks.append(Pick(i.t, "milestone", "Asked the interviewer", facts, 5))
            continue
        about = f" on step {i.step_id} ({steps[i.step_id]})" if i.step_id in steps else ""
        facts = f'A {i.level} ({i.trigger}){about}: "{i.text}"'
        if i.step_id is not None:
            done = _done_after(events, i.step_id, i.t)
            facts += (
                " The step wasn't done by the end."
                if done is None
                else f" Time to recover: the step was done {(done - i.t) // 1000} s later."
            )
        rank = 2 if i.level in (InterventionLevel.HINT, InterventionLevel.CONCEPT) else 3
        picks.append(Pick(i.t, "nudge", f"{i.level.capitalize()} from the interviewer", facts, rank))
    return picks


def _integrity_picks(events: Sequence[TimelineEvent]) -> list[Pick]:
    titles = {"paste": "Pasted code", "bulk_insert": "Large insert", "tab_hidden": "Left the tab"}
    return [
        Pick(f.t, "integrity", titles.get(f.kind, "Integrity note"), f.detail, 2)
        for f in payloads(events, TimelineKind.INTEGRITY, IntegrityFlag)
    ]


def _wrap_up_picks(events: Sequence[TimelineEvent]) -> list[Pick]:
    picks: list[Pick] = []
    spans = _phase_spans(events, None, {Phase.WRAP_UP})
    question: str | None = None
    for turn in payloads(events, TimelineKind.TRANSCRIPT, TranscriptTurn):
        if not turn.final or not any(a <= turn.start_ms < b for a, b in spans):
            continue
        if turn.speaker == "interviewer":
            question = turn.text
        elif question is not None:
            facts = f'Asked: "{question}" Answered: "{_cut(turn.text)}"'
            picks.append(Pick(turn.start_ms, "milestone", "Wrap-up answer", facts, 3))
            question = None
    return picks


def _defense_picks(events: Sequence[TimelineEvent]) -> list[Pick]:
    titles = {f.id: f.title for a in payloads(events, TimelineKind.AUDIT, AuditResult) for f in a.findings}
    picks: list[Pick] = []
    for e in events:
        if e.kind == TimelineKind.CHAOS_RUN:
            picks.extend(_chaos_pick(e.t, ChaosRun.model_validate(e.payload), titles))
        elif e.kind == TimelineKind.GRILL:
            g = GrillTurn.model_validate(e.payload)
            kind: MomentKind = "good" if g.score >= 7 else "issue" if g.score <= 4 else "milestone"
            root = "named the root cause" if g.root_cause_hit else "missed the root cause"
            facts = f"Grill on {titles.get(g.finding_id, g.finding_id)}: scored {g.score}/10, {root}."
            picks.append(Pick(e.t, kind, "Grill answer", f"{facts} {g.eval.feedback}", 2))
        elif e.kind == TimelineKind.VERDICT:
            v = Verdict.model_validate(e.payload)
            facts = ("Passed" if v.passed else "Did not pass") + ": " + "; ".join(v.reasons)
            picks.append(Pick(e.t, "good" if v.passed else "issue", "Verdict", facts, 1))
    return picks


def _chaos_pick(t: int, run: ChaosRun, titles: Mapping[str, str]) -> list[Pick]:
    if run.verdict == "error":
        return []
    name = titles.get(run.finding_id, run.finding_id)
    if run.kind == "baseline":
        broke = run.verdict == "broke"
        title = "Broke under load" if broke else "Held under load"
        return [
            Pick(t, "issue" if broke else "milestone", title, f"{name}: {run.summary}", 1 if broke else 4)
        ]
    held = run.verdict == "held"
    title = "Fix held" if held else "Fix didn't hold"
    return [Pick(t, "good" if held else "issue", title, f"{name}, attempt {run.attempt}: {run.summary}", 1)]


# --- the draft prompt ---------------------------------------------------------------------------------------


def draft_messages(
    rt: SessionRuntime,
    events: Sequence[TimelineEvent],
    end_ms: int,
    metrics: Metrics,
    picks: Sequence[Pick],
    extra: CodingExtra | DefenseExtra,
    context: RubricContext | None,
) -> list[dict[str, str]]:
    config = rt.session.config
    head = (
        f"# Session\nMode: {config.mode}. Length: {clock(end_ms)}. Voice: {'on' if config.voice else 'off'}. "
        f"Feedback: {config.feedback}."
    )
    sections = [
        head,
        _problem_section(context, extra),
        _code_section(rt, context),
        _progress_section(events, context),
        _conversation_section(events),
        "# Metrics (computed by code; exact)\n" + metrics.model_dump_json(indent=1),
        "# Candidate moments (write exactly one moment per line, same t and kind)\n"
        + "\n".join(
            json.dumps(CandidateMoment(t=p.t, kind=p.kind, facts=p.facts).model_dump()) for p in picks
        ),
    ]
    return [
        {"role": "system", "content": PROMPTS["report_system"]},
        {"role": "user", "content": "\n\n".join(s for s in sections if s)},
    ]


def _problem_section(context: RubricContext | None, extra: CodingExtra | DefenseExtra) -> str:
    if isinstance(extra, DefenseExtra):
        findings = "\n".join(
            f"- {f.id} {f.title} ({f.category}, {f.severity}): {f.explanation}" for f in extra.findings
        )
        runs = "\n".join(
            f"- {r.finding_id} {r.kind} attempt {r.attempt}: {r.verdict}. {r.summary}"
            for r in extra.chaos_runs
        )
        grill = "\n".join(
            f"- {g.finding_id}: Q: {g.question} Score {g.score}/10, root cause hit: {g.root_cause_hit}. "
            f"Feedback: {g.eval.feedback}"
            for g in extra.grill
        )
        v = extra.verdict
        verdict = (
            f"Passed: {v.passed}. Fixed: {v.findings_fixed}. Unfixed: {v.findings_unfixed}. "
            + "; ".join(v.reasons)
        )
        return (
            f"# Findings\n{findings or '(none)'}\n\n# Chaos runs\n{runs or '(none)'}\n\n"
            f"# Grill\n{grill or '(none)'}\n\n# Verdict\n{verdict}"
        )
    if context is None:
        return f"# Problem\n{extra.problem_slug}\n\n{_wrap_up_section(extra)}"
    steps = "\n".join(
        f"- {s.id} {s.title}{' (required)' if s.required else ''}: {s.description}" for s in context.steps
    )
    return (
        f"# Problem: {context.title}\n{context.brief_md}\n\n## Rubric steps\n{steps}\n\n"
        f"{_wrap_up_section(extra)}"
    )


def _wrap_up_section(extra: CodingExtra) -> str:
    """The approach and the complexity verdict, both decided by code (COD-5), so the review agrees with them."""
    verdict = {
        True: "matched an acceptable approach in the rubric",
        False: "did not match an acceptable approach in the rubric",
        None: "not graded (not asked, not answered, or grading failed); don't comment on it",
    }[extra.complexity_answer_ok]
    return f"# Wrap-up\nApproach: {extra.approach or '(not stated)'}\nComplexity answer: {verdict}"


def _code_section(rt: SessionRuntime, context: RubricContext | None) -> str:
    files = context.files if context and context.files else sorted(rt.code.code_by_file)
    parts = []
    for name in files:
        code = rt.code.code(name)
        if code.strip():
            parts.append(f"## {name}\n```python\n{code[:MAX_CODE_CHARS]}\n```")
    return "# Final code\n" + ("\n".join(parts) or "(no code)")


def _progress_section(events: Sequence[TimelineEvent], context: RubricContext | None) -> str:
    history, last = [], {}
    for e, a in _analyses(events):
        for s in a.steps:
            if last.get(s.step_id) != s.status:
                last[s.step_id] = s.status
                history.append(f"- {clock(e.t)} {s.step_id} → {s.status}: {s.evidence}")
    runs = "\n".join(
        f"- {clock(r.t)} {r.kind}: {r.passed}/{r.total} passed"
        + (f", compile error: {r.compile_error}" if r.compile_error else "")
        + (", timed out" if r.timed_out else "")
        for r in payloads(events, TimelineKind.RUN, RunResult)
    )
    if not history and not runs:
        return ""
    return f"# Step history\n{chr(10).join(history) or '(no analyses)'}\n\n# Runs\n{runs or '(none)'}"


def _conversation_section(events: Sequence[TimelineEvent]) -> str:
    turns = [t for t in payloads(events, TimelineKind.TRANSCRIPT, TranscriptTurn) if t.final][-MAX_TURNS:]
    transcript = "\n".join(f"- [{clock(t.start_ms)}] {t.speaker}: {_cut(t.text)}" for t in turns)
    shown = "\n".join(
        f"- [{clock(i.t)}] {i.level} ({i.trigger}{', ' + i.step_id if i.step_id else ''}): {i.text}"
        for i in help_shown(events)
    )
    return f"# Transcript\n{transcript or '(nothing said)'}\n\n# Interventions shown\n{shown or '(none)'}"


# --- merge (code decides) -----------------------------------------------------------------------------------


def merge(
    session_id: str,
    mode: Mode,
    draft: ReportDraft,
    metrics: Metrics,
    picks: Sequence[Pick],
    extra: CodingExtra | DefenseExtra,
    model_name: str,
    now: datetime,
) -> Report:
    """The draft's words with code's numbers: measured scores replace the model's, overall is their mean."""
    dimensions = _dimensions(mode, draft.dimensions, metrics, extra)
    overall = round(sum(d.score for d in dimensions) / len(dimensions) * 10) if dimensions else 0
    return Report(
        session_id=session_id,
        mode=mode,
        overall=overall,
        dimensions=dimensions,
        summary=draft.summary.strip(),
        strengths=_three(draft.strengths),
        improvements=_three(draft.improvements),
        moments=_moments(draft.moments, picks),
        metrics=metrics,
        coding=extra if isinstance(extra, CodingExtra) else None,
        defense=extra if isinstance(extra, DefenseExtra) else None,
        model=model_name,
        generated_at=now,
    )


def measured_scores(metrics: Metrics, extra: CodingExtra | DefenseExtra) -> dict[str, DimensionScore]:
    """Scores code can measure, which override the model's: hidden tests, fixes that held, grill scores."""
    scores: dict[str, DimensionScore] = {}
    if metrics.hidden_total:
        passed, total = metrics.hidden_passed or 0, metrics.hidden_total
        scores["correctness"] = _score(
            "correctness", 10 * passed / total, f"Passed {passed} of {total} hidden tests."
        )
    if isinstance(extra, DefenseExtra):
        v = extra.verdict
        broken = len(v.findings_fixed) + len(v.findings_unfixed)
        if broken:
            evidence = f"{len(v.findings_fixed)} of {broken} broken findings held after the fix."
            scores["correctness"] = _score("correctness", 10 * len(v.findings_fixed) / broken, evidence)
        else:
            scores["correctness"] = _score("correctness", 10, "Nothing broke under load.")
        if extra.grill:
            evidence = f"Average grill score {v.avg_grill_score:.1f}/10 over {len(extra.grill)} findings."
            scores["system_understanding"] = _score("system_understanding", v.avg_grill_score, evidence)
    return scores


def template_draft(
    metrics: Metrics,
    picks: Sequence[Pick],
    extra: CodingExtra | DefenseExtra,
    events: Sequence[TimelineEvent],
) -> ReportDraft:
    """The metrics-only report: measured scores, independence from the hints used, moments as facts."""
    scores = measured_scores(metrics, extra)
    if isinstance(extra, CodingExtra) and "correctness" not in scores:
        # No hidden-test result: the last run's visible tests, so an unfinished session can't score high.
        runs = payloads(events, TimelineKind.RUN, RunResult)
        last = runs[-1] if runs else None
        scores["correctness"] = (
            _score(
                "correctness",
                10 * last.passed / last.total,
                f"Last run passed {last.passed} of {last.total}.",
            )
            if last is not None and last.total
            else _score("correctness", 0, "No tests were run.")
        )
    cost = sum(HINT_COST[level] * n for level, n in metrics.hints_by_level.items())
    used = ", ".join(f"{n} {level}" for level, n in metrics.hints_by_level.items() if n) or "no hints"
    dimensions = [*scores.values(), _score("independence", 10 - cost, f"Used {used}.")]
    return ReportDraft(
        overall=0,  # merge() computes it
        dimensions=dimensions,
        summary=(
            "The written review couldn't be generated, so this report shows what was measured: the scores, "
            "metrics and moments below come straight from the session."
        ),
        strengths=[],
        improvements=[],
        moments=[Moment(t=p.t, kind=p.kind, title=p.title, detail=p.facts, tip=None) for p in picks],
    )


def _dimensions(
    mode: Mode, drafted: Iterable[DimensionScore], metrics: Metrics, extra: CodingExtra | DefenseExtra
) -> list[DimensionScore]:
    by_name: dict[str, DimensionScore] = {}
    for d in drafted:
        by_name.setdefault(d.name, d)
    measured = measured_scores(metrics, extra)
    out = []
    for name in DIMENSIONS[mode]:
        if name in measured:
            out.append(measured[name])
        elif name in by_name:
            d = by_name[name]
            out.append(_score(d.name, d.score, d.evidence))
    return out


def _moments(drafted: Iterable[Moment], picks: Sequence[Pick]) -> list[Moment]:
    """One moment per pick, in pick order: the model's wording at the same t, else the facts as they are."""
    by_t: dict[int, list[Moment]] = {}
    for m in drafted:
        by_t.setdefault(m.t, []).append(m)
    out = []
    for p in picks:
        worded = by_t.get(p.t)
        m = worded.pop(0) if worded else None
        if m is None or not m.title.strip() or not m.detail.strip():
            out.append(Moment(t=p.t, kind=p.kind, title=p.title, detail=p.facts, tip=None))
        else:
            out.append(Moment(t=p.t, kind=p.kind, title=m.title, detail=m.detail, tip=m.tip or None))
    return out


def _score(name: str, value: float, evidence: str) -> DimensionScore:
    return DimensionScore.model_validate(
        {"name": name, "score": max(0, min(10, round(value))), "evidence": evidence}
    )


def _three(items: Iterable[str]) -> list[str]:
    return [s.strip() for s in items if s.strip()][:3]


# --- helpers ------------------------------------------------------------------------------------------------


def payloads[T: BaseModel](events: Iterable[TimelineEvent], kind: TimelineKind, model: type[T]) -> list[T]:
    return [model.model_validate(e.payload) for e in events if e.kind == kind]


def step_titles(context: RubricContext | None) -> dict[str, str]:
    return {s.id: s.title for s in context.steps} if context else {}


def clock(ms: int) -> str:
    seconds = max(0, ms) // 1000
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _analyses(events: Iterable[TimelineEvent]) -> list[tuple[TimelineEvent, Analysis]]:
    return [(e, Analysis.model_validate(e.payload)) for e in events if e.kind == TimelineKind.ANALYSIS]


def _done_after(events: Sequence[TimelineEvent], step_id: str, t: int) -> int | None:
    for e, a in _analyses(events):
        if e.t > t and any(s.step_id == step_id and s.status == StepStatus.DONE for s in a.steps):
            return e.t
    return None


def _phase_spans(
    events: Sequence[TimelineEvent], end_ms: int | None, phases: Iterable[Phase]
) -> list[tuple[int, int]]:
    """(start, stop) of each stretch spent in one of `phases`."""
    wanted = set(phases)
    changes = payloads(events, TimelineKind.PHASE, PhaseChange)
    times = [e.t for e in events if e.kind == TimelineKind.PHASE]
    stop_all = end_ms if end_ms is not None else max((e.t for e in events), default=0) + 1
    spans = []
    for index, (t, change) in enumerate(zip(times, changes, strict=True)):
        if change.to_phase in wanted:
            stop = times[index + 1] if index + 1 < len(times) else stop_all
            spans.append((t, min(stop, stop_all)))
    return spans


def _hidden_ms(edits: Sequence[EditorEvent], end_ms: int) -> int:
    total, hidden_since = 0, None
    for e in edits:
        if e.kind == "hidden" and hidden_since is None:
            hidden_since = e.t
        elif e.kind == "visible" and hidden_since is not None:
            total += e.t - hidden_since
            hidden_since = None
    if hidden_since is not None:
        total += max(0, end_ms - hidden_since)
    return total


def _pasted(e: EditorEvent) -> int:
    return e.pasted_chars if e.pasted_chars is not None else sum(len(c.text) for c in e.changes)


def _cut(text: str) -> str:
    return text if len(text) <= MAX_TURN_CHARS else text[: MAX_TURN_CHARS - 1] + "…"
