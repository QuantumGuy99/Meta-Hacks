"""Validate the Defense sample apps (DATA-2, PLAN §13.2): each app boots, every reference attack breaks the
original code, and the same attack holds once the reference fix is applied.

    uv run python -m crucible.datatools.validate_apps --all [--runs 5] [--duration 6]
    uv run python -m crucible.datatools.validate_apps bank-transfer

It goes through the same loader, AST validator and chaos runner a live session uses, so a pass here means the
demo path works on this data.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass, field

from crucible.config import get_settings
from crucible.contracts.defense import ChaosRun
from crucible.defense.audit import audit_from_flaws
from crucible.defense.chaos import run_attack
from crucible.defense.ports import MemorySink
from crucible.defense.projects import Sample, apply_patch, load_samples
from crucible.defense.validator import AttackRejected, validate_functions
from crucible.runner.base import Runner

ERRORS_REASON = "of requests failed"  # chaos.decide_verdict's wording for the >5% error rule
REQUIRED_FLAW_KEYS = (
    "id",
    "category",
    "file",
    "line_start",
    "line_end",
    "explanation",
    "expected_fix",
    "grill_expected_points",
    "chaos_invariant",
)


@dataclass(slots=True)
class AppReport:
    slug: str
    errors: list[str] = field(default_factory=list)
    runs: list[str] = field(default_factory=list)  # one line per attack run, for the console

    @property
    def ok(self) -> bool:
        return not self.errors


def static_checks(sample: Sample, patch_text: str | None) -> list[str]:
    """Ground truth and reference fix agree with the code. No app runs."""
    errors: list[str] = []
    files = sample.files
    for i, flaw in enumerate(sample.flaws):
        missing = [k for k in REQUIRED_FLAW_KEYS if k not in flaw]
        if missing:
            errors.append(f"flaws.json entry {i} is missing {missing}")
            continue
        lines = files.get(flaw["file"], "").count("\n") + 1
        if flaw["file"] not in files:
            errors.append(f"{flaw['id']}: {flaw['file']} isn't in app/")
        elif not 1 <= flaw["line_start"] <= flaw["line_end"] <= lines:
            errors.append(
                f"{flaw['id']}: lines {flaw['line_start']}–{flaw['line_end']} are outside {flaw['file']}"
            )
        if not 2 <= len(flaw["grill_expected_points"]) <= 4:
            errors.append(f"{flaw['id']}: {len(flaw['grill_expected_points'])} grill points (want 2–4)")
    if not sample.reference_attacks:
        errors.append("no reference_attack.json")
    flaw_ids = {f.get("id") for f in sample.flaws}
    for ref in sample.reference_attacks:
        if ref.flaw_id is not None and ref.flaw_id not in flaw_ids:
            errors.append(f"reference attack for unknown flaw {ref.flaw_id}")
        try:
            validate_functions(ref.functions)
        except AttackRejected as exc:
            errors.append(f"the validator rejects the reference attack for {ref.flaw_id}: {exc}")
    if sample.fixed_files is None:
        errors.append("no reference fix (fix.patch or fixed/)")
    elif patch_text is not None and apply_patch(files, patch_text) != sample.fixed_files:
        errors.append("fix.patch and fixed/ disagree")
    return errors


async def check_app(
    sample: Sample, patch_text: str | None, runner: Runner, *, runs: int, duration_s: int | None
):
    report = AppReport(sample.project.id, errors=static_checks(sample, patch_text))
    if report.errors:
        return report
    findings = {f.id: f for f in audit_from_flaws(sample).findings}
    first_chaos = next((fid for fid, f in findings.items() if f.chaos), None)
    for ref in sample.reference_attacks:
        finding = findings.get(ref.flaw_id or first_chaos or "")
        if finding is None or finding.chaos is None:
            report.errors.append(f"reference attack {ref.flaw_id} has no finding with a chaos plan")
            continue
        for attempt in range(1, runs + 1):
            for kind, files, want in (
                ("baseline", sample.files, "broke"),
                ("verify", sample.fixed_files, "held"),
            ):
                run = await run_attack(
                    runner, sample.project, files or {}, finding, ref.functions, MemorySink(),
                    kind=kind, attempt=attempt, duration_override_s=duration_s,
                )  # fmt: skip
                report.runs.append(f"{finding.id} {kind} #{attempt}: {run.verdict} | {run.summary}")
                if run.verdict != want:
                    report.errors.append(_mismatch(finding.id, kind, want, run))
                elif kind == "baseline" and breaks_on_errors(run):
                    report.errors.append(
                        f"{finding.id}: the attack breaks on failed requests, not only its invariant, so the "
                        f"headline undersells it (lower the concurrency or make requests cheaper): {run.detail}"
                    )
    return report


def breaks_on_errors(run: ChaosRun) -> bool:
    """The run's error rate alone would break it (chaos.decide_verdict's >5% rule). A reference attack should
    break on its invariant, whose detail is the headline on screen, with requests that still succeed."""
    return run.verdict == "broke" and ERRORS_REASON in run.detail


# --- private helpers ------------------------------------------------------------------------------------------


def _mismatch(finding_id: str, kind: str, want: str, run: ChaosRun) -> str:
    code = "original code" if kind == "baseline" else "reference fix"
    return f"{finding_id}: the {code} should have {want} but {run.verdict}: {run.summary}"


async def _validate(slugs: list[str], runner: Runner, runs: int, duration_s: int | None) -> list[AppReport]:
    s = get_settings()
    samples = load_samples(s.DEFENSE_APPS_DIR)
    reports = []
    for slug in slugs:
        sample = samples.get(slug)
        if sample is None:
            reports.append(AppReport(slug, errors=["doesn't load (see the log above) or doesn't exist"]))
            continue
        patch = s.DEFENSE_APPS_DIR / slug / "fix.patch"
        text = patch.read_text(encoding="utf-8") if patch.exists() else None
        reports.append(await check_app(sample, text, runner, runs=runs, duration_s=duration_s))
    return reports


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m crucible.datatools.validate_apps")
    ap.add_argument("slugs", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument(
        "--runs", type=int, default=1, help="repeat each attack (the demo app: 5, PLAN risk list)"
    )
    ap.add_argument("--duration", type=int, default=None, help="attack seconds (default: the app's own)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    s = get_settings().model_copy(update={"RUNNER": "local", "ALLOW_LOCAL_RUNNER": True})
    if args.all:
        args.slugs = sorted(p.name for p in s.DEFENSE_APPS_DIR.iterdir() if (p / "app").is_dir())
    if not args.slugs:
        ap.error("name an app or pass --all")
    from crucible.runner.local import LocalRunner  # dev tool: apps are checked locally; Modal is RUN-3's job

    reports = asyncio.run(_validate(args.slugs, LocalRunner(s), args.runs, args.duration))
    for r in reports:
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.slug}")
        for line in r.runs:
            print(f"      {line}")
        for e in r.errors:
            print(f"      error: {e}")
    passed = sum(r.ok for r in reports)
    print(f"\n{passed} of {len(reports)} apps pass")
    return 0 if passed == len(reports) else 1


if __name__ == "__main__":
    sys.exit(main())
