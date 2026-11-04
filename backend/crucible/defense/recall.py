"""Audit recall eval (DEF-2 step 4, PLAN §16): every seeded flaw is found in ≥ 2 of 3 model audits.

    uv run python -m crucible.defense.recall [--runs 3] [bank-transfer ...]

Reads data/evals/defense/<app>.json. A finding matches a seeded flaw when it names the same file and category
and its lines overlap. Calls the real audit model (costs credits); the flaws.json fallback never counts.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from crucible.config import REPO_ROOT, get_settings
from crucible.contracts.defense import Finding
from crucible.defense.audit import audit_with_model
from crucible.defense.model_client import WrapperModelClient
from crucible.defense.ports import MemorySink, ModelClient, ModelUnavailable
from crucible.defense.projects import Sample, load_samples

EVALS_DIR = REPO_ROOT / "data" / "evals" / "defense"
RUNS = 3
MIN_HITS = 2


@dataclass(slots=True)
class ExpectedFinding:
    flaw_id: str
    file: str
    line_start: int
    line_end: int
    category: str


@dataclass(slots=True)
class RecallReport:
    app: str
    runs: int
    hits: dict[str, int] = field(default_factory=dict)  # flaw_id → runs that found it
    failed_runs: list[str] = field(default_factory=list)  # why a run produced no audit

    def passed(self, min_hits: int = MIN_HITS) -> bool:
        return bool(self.hits) and all(n >= min_hits for n in self.hits.values())


def matched_flaws(expected: list[ExpectedFinding], findings: list[Finding]) -> set[str]:
    """Seeded flaws the audit found: same file, same category, overlapping lines; each finding counts once."""
    unused = list(findings)
    found: set[str] = set()
    for e in expected:
        hit = next((f for f in unused if _matches(e, f)), None)
        if hit is not None:
            unused.remove(hit)
            found.add(e.flaw_id)
    return found


async def audit_recall(
    sample: Sample, expected: list[ExpectedFinding], llm: ModelClient, *, runs: int = RUNS
):
    report = RecallReport(sample.project.id, runs, hits={e.flaw_id: 0 for e in expected})
    for i in range(runs):
        try:
            audit = await audit_with_model(sample, llm, MemorySink())
        except ModelUnavailable as exc:
            report.failed_runs.append(f"run {i + 1}: {exc}")
            continue
        for flaw_id in matched_flaws(expected, audit.findings):
            report.hits[flaw_id] += 1
    return report


def load_eval(path: Path) -> tuple[str, list[ExpectedFinding]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw["app"], [ExpectedFinding(**e) for e in raw["expected_findings"]]


# --- private helpers ------------------------------------------------------------------------------------------


def _matches(e: ExpectedFinding, f: Finding) -> bool:
    return (
        f.file == e.file
        and f.category == e.category
        and f.line_start <= e.line_end
        and e.line_start <= f.line_end
    )


async def _run_all(apps: list[str], runs: int) -> list[RecallReport]:
    samples = load_samples(get_settings().DEFENSE_APPS_DIR)
    llm = WrapperModelClient()
    reports = []
    for path in sorted(EVALS_DIR.glob("*.json")):
        app, expected = load_eval(path)
        if apps and app not in apps:
            continue
        if app not in samples:
            reports.append(RecallReport(app, runs, failed_runs=[f"sample {app} doesn't load"]))
            continue
        reports.append(await audit_recall(samples[app], expected, llm, runs=runs))
    return reports


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m crucible.defense.recall")
    ap.add_argument("apps", nargs="*")
    ap.add_argument("--runs", type=int, default=RUNS)
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    from crucible.main import _configure_models

    if _configure_models(get_settings()) is None:
        print("MODEL_API_KEY isn't set in .env; the recall eval needs the audit model", file=sys.stderr)
        return 2
    reports = asyncio.run(_run_all(args.apps, args.runs))
    need = min(MIN_HITS, args.runs)
    for r in reports:
        print(f"{'PASS' if r.passed(need) else 'FAIL'}  {r.app}")
        for flaw_id, n in r.hits.items():
            print(f"      {flaw_id}: found in {n} of {r.runs} runs")
        for why in r.failed_runs:
            print(f"      no audit: {why}")
    return 0 if reports and all(r.passed(need) for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
