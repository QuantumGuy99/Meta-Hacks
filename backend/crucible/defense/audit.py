"""Audit: Wonder → Spark → the sample's flaws.json, then code checks the result (PLAN §11.3)."""

from __future__ import annotations

import logging
import re
from pathlib import PurePosixPath

from pydantic import ValidationError

from crucible.contracts.coding import RubricStep
from crucible.contracts.defense import (
    AuditResult,
    ChaosPlan,
    Finding,
    GrillSpec,
    TopologyEdge,
    TopologyNode,
)
from crucible.defense.ports import EventSink, ModelClient, ModelUnavailable, note
from crucible.defense.projects import ReferenceAttack, Sample, numbered_source
from crucible.defense.prompts import PROMPTS

logger = logging.getLogger(__name__)

AUDIT_TIMEOUT_S = 120
SEVERITY_ORDER: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}
MAX_FINDINGS = 5
# Words that name a cause or a fix. The summary and titles are shown before the grill, so a title with any
# of these is replaced with a neutral one (the prompt asks for area-only wording; code makes sure).
_CAUSE_WORDS = re.compile(
    r"race|lock|mutex|atomic|await|async|concurren|synchron|stale|snapshot|lost update|overwrit|interleav"
    r"|transaction|blocking|block|quadratic|o\(n|n\^?2|n²|deadlock|leak|unbounded|injection|sleep",
    re.IGNORECASE,
)
GENERIC_QUESTION = "Crucible's load test broke this part of the app. Walk me through what happened, and why."
GENERIC_FOLLOW_UP = (
    "What exactly happens between the moment a request reads the data and the moment it writes?"
)


class AuditFailed(Exception):
    """No model answered and there's no ground truth to fall back to (uploads)."""


_CACHE: dict[str, AuditResult] = {}  # content_hash → result; store/ persists this later (DEF-2)


async def run_audit(
    sample: Sample, llm: ModelClient, sink: EventSink, *, use_cache: bool = True
) -> AuditResult:
    key = sample.project.content_hash
    if use_cache and key in _CACHE:
        return _CACHE[key]
    try:
        result = await _model_audit(sample, llm, sink)
    except ModelUnavailable as exc:
        if not sample.flaws:
            raise AuditFailed(f"audit models unavailable and no flaws.json: {exc}") from exc
        await note(
            sink, "warning", f"Audit models unavailable; using {sample.project.id}/flaws.json. ({exc})"
        )
        result = audit_from_flaws(sample)
    if not result.findings and sample.flaws:
        await note(sink, "warning", f"The audit found nothing twice; using {sample.project.id}/flaws.json.")
        result = audit_from_flaws(sample)
    _CACHE[key] = result
    return result


async def _model_audit(sample: Sample, llm: ModelClient, sink: EventSink) -> AuditResult:
    """One retry when the audit comes back empty: Wonder returned no findings in 2 of 6 live runs (#43)."""
    raw = await llm.complete_json("audit", _messages(sample), AuditResult, timeout_s=AUDIT_TIMEOUT_S)
    result = check_audit(raw, sample.files)
    if result.findings:
        return result
    await note(sink, "warning", "The audit found nothing; asking once more.")
    raw = await llm.complete_json("audit", _messages(sample), AuditResult, timeout_s=AUDIT_TIMEOUT_S)
    return check_audit(raw, sample.files)


def check_audit(a: AuditResult, files: dict[str, str]) -> AuditResult:
    """Code decides: valid node ids, flagged nodes, line ranges in bounds, ≤ 5 findings by severity, and
    pre-grill wording that can't give the answer away (a code-built summary, neutral titles)."""
    node_ids = {n.id for n in a.nodes}
    findings: list[Finding] = []
    for f in a.findings:
        if f.file not in files:
            logger.warning("dropping finding %s: unknown file %s", f.id, f.file)
            continue
        n_lines = files[f.file].count("\n") + 1
        start = max(1, min(f.line_start, n_lines))
        end = max(start, min(f.line_end, n_lines))
        findings.append(
            f.model_copy(
                update={
                    "node_id": f.node_id if f.node_id in node_ids else None,
                    "line_start": start,
                    "line_end": end,
                    "title": neutral_title(f.title, f.file),
                }
            )
        )
    findings.sort(key=lambda f: SEVERITY_ORDER[f.severity])
    findings = findings[:MAX_FINDINGS]
    flagged = {f.node_id for f in findings if f.node_id}
    nodes = [n.model_copy(update={"flagged": n.id in flagged}) for n in a.nodes]
    edges = [e for e in a.edges if e.source in node_ids and e.target in node_ids]
    return AuditResult(summary=public_summary(len(findings)), nodes=nodes, edges=edges, findings=findings)


def neutral_title(title: str, file: str) -> str:
    """The model's title if it names only the area, else "<file> under load"."""
    if _CAUSE_WORDS.search(title):
        return f"{PurePosixPath(file).name} under load"
    return title


def public_summary(n_findings: int) -> str:
    """Built in code, never by the model: Wonder's own summary stated the root cause in a live run (#22)."""
    if n_findings == 0:
        return "Nothing in this project stood out as risky under load."
    if n_findings == 1:
        return "1 area of this project needs a closer look under load."
    return f"{n_findings} areas of this project need a closer look under load."


def audit_from_flaws(sample: Sample) -> AuditResult:
    """Ground-truth fallback for sample apps (logged; never presented as an AI result in the demo)."""
    nodes, edges = derive_topology(sample.files)
    by_file = {n.file: n.id for n in nodes if n.file}
    findings = []
    for i, flaw in enumerate(sample.flaws):
        try:
            findings.append(_finding_from_flaw(flaw, i, by_file.get(flaw["file"]), sample.reference_attack))
        except (KeyError, ValidationError) as exc:
            logger.error("flaws.json entry %d in %s is invalid: %s", i, sample.project.id, exc)
    result = AuditResult(
        summary="",  # check_audit writes the public summary
        nodes=nodes,
        edges=edges,
        findings=findings,
    )
    return check_audit(result, sample.files)


def derive_topology(files: dict[str, str]) -> tuple[list[TopologyNode], list[TopologyEdge]]:
    """One node per Python module, edges from imports. Crude but honest; the model's topology is richer."""
    modules = {_module(p): p for p in files if p.endswith(".py") and not p.endswith("__init__.py")}
    nodes = [
        TopologyNode(
            id=mod, label=PurePosixPath(path).name, kind=_kind(path, files[path]), file=path, flagged=False
        )
        for mod, path in sorted(modules.items())
    ]
    edges = []
    for mod, path in sorted(modules.items()):
        for target in sorted(modules):
            if target != mod and _imports(files[path], target):
                edges.append(TopologyEdge(source=mod, target=target, label=None))
    return nodes, edges


def _imports(source: str, module: str) -> bool:
    """`import app.ledger`, `from app.ledger import x` or `from app import ledger`."""
    if re.search(rf"(from|import)\s+{re.escape(module)}\b", source):
        return True
    package, _, name = module.rpartition(".")
    return bool(package) and bool(
        re.search(rf"from\s+{re.escape(package)}\s+import\s+[^\n]*\b{re.escape(name)}\b", source)
    )


def _finding_from_flaw(flaw: dict, i: int, node_id: str | None, ref: ReferenceAttack | None) -> Finding:
    chaos_extra = flaw.get("chaos") or {}
    use_ref = ref is not None and (ref.flaw_id in (None, flaw.get("id")))
    chaos = (
        ChaosPlan(
            endpoint=chaos_extra.get("endpoint", flaw.get("endpoint", "")),
            method=chaos_extra.get("method", "POST"),
            body_example=chaos_extra.get("body_example"),
            concurrency=ref.concurrency if use_ref else int(chaos_extra.get("concurrency", 100)),
            duration_s=ref.duration_s if use_ref else int(chaos_extra.get("duration_s", 10)),
            invariant=flaw.get("chaos_invariant", chaos_extra.get("invariant", "")),
            p95_threshold_ms=chaos_extra.get("p95_threshold_ms"),
        )
        if (use_ref or chaos_extra or flaw.get("chaos_invariant"))
        else None
    )
    expected_fix = flaw.get("expected_fix", "Make the operation safe under concurrent requests.")
    steps = flaw.get("fix_steps") or [
        {
            "id": "s1",
            "title": "Make the critical section safe",
            "description": expected_fix,
            "required": True,
            "order": 1,
            "look_for": [],
            "hints": [
                "Look at what happens between reading the data and writing it back.",
                "What could another request do while this one is waiting?",
                "Make the read and the write one indivisible step.",
            ],
        }
    ]
    return Finding(
        id=flaw.get("id", f"f{i + 1}"),
        title=flaw.get("title") or f"{PurePosixPath(flaw['file']).name} under concurrent load",
        category=flaw["category"],
        severity=flaw.get("severity", "high"),
        file=flaw["file"],
        line_start=int(flaw["line_start"]),
        line_end=int(flaw["line_end"]),
        node_id=node_id,
        explanation=flaw["explanation"],
        chaos=chaos,
        grill=GrillSpec(
            question=flaw.get("grill_question", GENERIC_QUESTION),
            expected_points=list(flaw["grill_expected_points"]),
            follow_up=flaw.get("grill_follow_up", GENERIC_FOLLOW_UP),
        ),
        fix_steps=[RubricStep.model_validate(s) for s in steps],
    )


def _module(path: str) -> str:
    return path.removesuffix(".py").replace("/", ".")


def _kind(path: str, src: str) -> str:
    name = PurePosixPath(path).stem.lower()
    if any(k in name for k in ("db", "store", "repo", "model")):
        return "store"
    if "worker" in name or "task" in name:
        return "worker"
    if re.search(r"@(app|router)\.(get|post|put|patch|delete)\(", src):
        return "route"
    return "service"


def _messages(sample: Sample) -> list[dict]:
    return [
        {"role": "system", "content": PROMPTS["audit_system"]},
        {"role": "user", "content": numbered_source(sample.files)},
    ]
