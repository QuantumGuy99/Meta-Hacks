"""The end-of-session report (PLAN §7.5). Metrics come from code; the LLM only words the draft."""

from datetime import datetime
from typing import Literal

from crucible.contracts.coding import StepProgress
from crucible.contracts.common import Mode, Strict
from crucible.contracts.defense import ChaosRun, Finding, GrillTurn, Verdict

MomentKind = Literal["good", "issue", "nudge", "integrity", "milestone"]


class Moment(Strict):
    t: int
    kind: MomentKind
    title: str
    detail: str
    tip: str | None


class DimensionScore(Strict):
    name: Literal[
        "problem_solving",
        "correctness",
        "code_quality",
        "communication",
        "independence",
        "debugging",
        "system_understanding",
    ]
    score: int  # 0–10
    evidence: str


class Metrics(Strict):  # computed in code, never by the LLM
    duration_s: int
    time_to_first_edit_s: int | None
    time_to_first_run_s: int | None
    runs: int
    submits: int
    hidden_passed: int | None
    hidden_total: int | None
    interventions_shown: int
    hints_by_level: dict[str, int]
    chars_typed: int
    chars_pasted: int
    tab_hidden_s: int
    talk_time_s: int
    longest_silence_s: int


class CandidateMoment(Strict):  # selected by code, worded by the LLM
    t: int
    kind: MomentKind
    facts: str


class ReportDraft(Strict):  # LLM output (Wonder)
    overall: int  # 0–100
    dimensions: list[DimensionScore]
    summary: str
    strengths: list[str]  # 3
    improvements: list[str]  # 3
    moments: list[Moment]  # one per CandidateMoment, same t


class CodingExtra(Strict):
    problem_slug: str
    steps: list[StepProgress]  # final statuses
    approach: str | None
    complexity_answer_ok: bool | None


class DefenseExtra(Strict):
    findings: list[Finding]
    chaos_runs: list[ChaosRun]  # baseline + verify runs carry the before/after metrics
    grill: list[GrillTurn]
    verdict: Verdict
    card_url: str | None  # P2: merge-gate card image (§11.8)


class Report(Strict):
    session_id: str
    mode: Mode
    overall: int
    dimensions: list[DimensionScore]
    summary: str
    strengths: list[str]
    improvements: list[str]
    moments: list[Moment]
    metrics: Metrics
    coding: CodingExtra | None
    defense: DefenseExtra | None
    model: str
    generated_at: datetime
