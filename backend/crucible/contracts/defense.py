"""Project Defense: projects, the audit, chaos runs, the grill and the verdict (PLAN §7.4)."""

from typing import Literal

from crucible.contracts.coding import RubricStep
from crucible.contracts.common import Strict

FindingCategory = Literal[
    "race_condition", "blocking_io", "complexity", "resource_leak", "error_handling", "security"
]
Severity = Literal["low", "medium", "high", "critical"]


class ProjectFile(Strict):
    path: str
    size: int


class Project(Strict):
    id: str
    name: str
    source: Literal["sample", "upload", "github"]
    entrypoint: str  # e.g. "uvicorn app.main:app --host 127.0.0.1 --port 8080"
    port: int  # 8080 (keeps clear of the backend's :8000 under LocalRunner)
    files: list[ProjectFile]
    loc: int
    content_hash: str  # sha256 of sorted files; audit cache key


class TopologyNode(Strict):
    id: str
    label: str
    kind: Literal["route", "service", "store", "external", "worker"]
    file: str | None
    flagged: bool


class TopologyEdge(Strict):
    source: str
    target: str
    label: str | None


class ChaosPlan(Strict):
    endpoint: str  # "/transfer"
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    body_example: str | None  # JSON text
    concurrency: int  # ≤ 200
    duration_s: int  # ≤ 30
    invariant: str  # "sum of all balances stays 10000"
    p95_threshold_ms: int | None  # latency findings: p95 above this = broke; None = no latency check


class GrillSpec(Strict):
    question: str
    expected_points: list[str]  # 2–4; [0] is ALWAYS the root cause (audit prompt rule)
    follow_up: str


class Finding(Strict):
    id: str
    title: str  # neutral: names the area, not the cause ("Balance transfers under load")
    category: FindingCategory
    severity: Severity
    file: str
    line_start: int
    line_end: int
    node_id: str | None  # the TopologyNode this flaw lives in (highlighting, SAM bonus)
    explanation: str  # grading truth: never sent to the browser before this finding's grill ends
    chaos: ChaosPlan | None
    grill: GrillSpec
    fix_steps: list[RubricStep]  # rubric for the fix stage (same engine as coding mode)


class FindingPublic(Strict):  # what the browser gets until the finding's grill is graded
    id: str
    title: str
    category: FindingCategory
    severity: Severity
    file: str
    line_start: int
    line_end: int
    node_id: str | None


class AuditResult(Strict):  # LLM output (Wonder)
    summary: str  # must not state root causes or fixes (it's shown before the grill)
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    findings: list[Finding]  # sorted by severity, max 5


class AuditPublic(Strict):  # payload of WS defense.audit
    summary: str
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    findings: list[FindingPublic]


class AttackFunctions(Strict):  # LLM output (Glimmer/Spark): bodies for the template (§11.4)
    setup_body: str
    request_body: str
    invariant_body: str
    rationale: str


class ChaosMetric(Strict):
    run_id: str
    t_ms: int  # ms since the attack started
    in_flight: int  # concurrent requests open at the end of the window
    rps: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    errors: int
    violations: int


class ChaosRun(Strict):
    id: str
    finding_id: str
    kind: Literal["baseline", "verify"]
    attempt: int
    script: str
    verdict: Literal["broke", "held", "error"]
    summary: str  # from the real run: "37 of 500 orders lost; $1,240 missing"
    detail: str
    metrics: list[ChaosMetric]


class GrillEval(Strict):  # LLM output: judgements only, NO score (code computes it, §11.5)
    points_hit: list[int]  # indexes into GrillSpec.expected_points
    points_missed: list[int]
    needs_follow_up: bool
    feedback: str  # passes the leak guard (§9.6) before it reaches the browser


class GrillTurn(Strict):
    finding_id: str
    question: str
    answer_turn_ids: list[str]
    follow_up_asked: bool
    eval: GrillEval
    sam_node_id: str | None  # node the candidate circled (P1, §11.7)
    root_cause_hit: bool  # computed: 0 in eval.points_hit
    score: int  # computed: 0–10 (§11.5)


class SamHighlight(Strict):  # P1: candidate circled part of the diagram or a sketch (§11.7)
    finding_id: str
    source: Literal["canvas", "webcam"]
    box: list[float] | None  # [x1, y1, x2, y2] in image pixels; None = nothing found
    node_id: str | None  # node chosen by code from the box (largest overlap)


class Verdict(Strict):
    passed: bool
    reasons: list[str]
    findings_fixed: list[str]
    findings_unfixed: list[str]
    avg_grill_score: float
