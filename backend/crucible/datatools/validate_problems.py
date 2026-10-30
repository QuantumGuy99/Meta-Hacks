"""Validate problems against the PLAN §13.1 bar: schema, tests, brute force, starter, rubric (DATA-2).

    uv run python -m crucible.datatools.validate_problems --all
    uv run python -m crucible.datatools.validate_problems room-bookings [--drafts]

Errors fail the problem (and the exit code); warnings are quality-bar notes for the human review.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from crucible.coding.problems import DEFAULT_ROOT, load_problem
from crucible.config import get_settings
from crucible.contracts.coding import CaseSpec, ProblemSpec
from crucible.engine.interviewer import looks_like_code
from crucible.runner.base import RunLimits, Runner, RunRequest

BRUTE_CASES = 200
BRUTE_TIMEOUT_S = 60.0
HINTS_PER_STEP = 3
STEPS_RANGE = (3, 6)
VISIBLE_RANGE = (2, 4)
HIDDEN_RANGE = (8, 25)
WRAP_UPS = 2
TIME_LIMITS = {"easy": 20, "medium": 30, "hard": 40}
SUITE_LIMITS = RunLimits(per_test_s=2.0, total_s=30.0)
# Runs gen.py and brute.py from a problem folder in an isolated interpreter and prints [[args, expected], ...].
_BRUTE_SCRIPT = """
import importlib.util, json, random, sys
def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
folder, fn, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
gen, brute = load(folder + "/gen.py", "gen"), load(folder + "/brute.py", "brute")
out = []
for seed in range(n):
    args = gen.generate(random.Random(seed))
    out.append([args, getattr(brute, fn)(*json.loads(json.dumps(args)))])
print(json.dumps(out))
"""


@dataclass(slots=True)
class ProblemReport:
    slug: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def static_checks(spec: ProblemSpec) -> tuple[list[str], list[str]]:
    """(errors, warnings) from the problem alone: the rubric quality bar in PLAN §13.1. No code runs."""
    errors: list[str] = []
    warnings: list[str] = []
    steps = spec.rubric.steps
    if not STEPS_RANGE[0] <= len(steps) <= STEPS_RANGE[1]:
        errors.append(f"{len(steps)} rubric steps (want {STEPS_RANGE[0]}–{STEPS_RANGE[1]})")
    for step in steps:
        if len(step.hints) != HINTS_PER_STEP:
            errors.append(f"step {step.id} has {len(step.hints)} hints (want exactly {HINTS_PER_STEP})")
        for i, hint in enumerate(step.hints):
            if looks_like_code(hint):
                errors.append(f"step {step.id} hint {i + 1} contains code (leak guard)")
        if not step.look_for:
            warnings.append(f"step {step.id} has no look_for signals")
    tested = {c.edge_case_id for c in [*spec.tests_visible, *spec.tests_hidden] if c.edge_case_id}
    for edge in spec.rubric.edge_cases:
        if edge.id not in tested:
            errors.append(f"edge case {edge.id} has no test (set edge_case_id on a hidden test)")
    unknown = tested - {e.id for e in spec.rubric.edge_cases}
    if unknown:
        errors.append(f"tests point at unknown edge cases {sorted(unknown)}")
    ids = [c.id for c in [*spec.tests_visible, *spec.tests_hidden]]
    if len(ids) != len(set(ids)):
        errors.append("two tests share an id")
    if len(spec.rubric.wrap_up_questions) != WRAP_UPS:
        errors.append(f"{len(spec.rubric.wrap_up_questions)} wrap-up questions (want {WRAP_UPS})")
    if spec.time_limit_min <= 0:
        errors.append("time_limit_min isn't set")
    elif spec.time_limit_min != TIME_LIMITS[spec.difficulty]:
        warnings.append(
            f"time limit {spec.time_limit_min} min ({spec.difficulty} is usually {TIME_LIMITS[spec.difficulty]})"
        )
    _count("visible tests", len(spec.tests_visible), VISIBLE_RANGE, warnings)
    _count("hidden tests", len(spec.tests_hidden), HIDDEN_RANGE, warnings)
    return errors, warnings


async def check_problem(folder: Path, runner: Runner) -> ProblemReport:
    report = ProblemReport(folder.name)
    try:
        spec = load_problem(folder)
    except (OSError, ValueError) as exc:  # json.JSONDecodeError and ValidationError are ValueErrors
        report.errors.append(f"doesn't load: {exc}")
        return report
    report.errors, report.warnings = static_checks(spec)
    cases = [*spec.tests_visible, *spec.tests_hidden]
    ref = await _run(runner, spec, spec.reference_solution, cases)
    if ref.compile_error or ref.timed_out or ref.passed != ref.total:
        failed = [c.id for c in ref.cases if not c.passed]
        report.errors.append(f"reference fails {failed or 'to run'}: {ref.compile_error or ''}".strip())
    starter = await _run(runner, spec, spec.starter_code, cases)
    if starter.compile_error:
        report.errors.append(f"starter code doesn't compile: {starter.compile_error}")
    elif starter.passed == starter.total:
        report.errors.append("starter code passes every test")
    if (folder / "gen.py").exists() and (folder / "brute.py").exists():
        report.errors += await _brute_agrees(folder, spec, runner)
    elif spec.difficulty != "easy":
        report.warnings.append("no gen.py + brute.py (recommended for medium and hard)")
    return report


async def validate(folders: list[Path], runner: Runner) -> list[ProblemReport]:
    return [await check_problem(f, runner) for f in folders]


def coverage(specs: list[ProblemSpec]) -> Counter[str]:
    return Counter(s.difficulty for s in specs)


# --- private helpers ------------------------------------------------------------------------------------------


def _count(label: str, n: int, bounds: tuple[int, int], warnings: list[str]) -> None:
    if not bounds[0] <= n <= bounds[1]:
        warnings.append(f"{n} {label} (want {bounds[0]}–{bounds[1]})")


async def _run(runner: Runner, spec: ProblemSpec, code: str, cases: list[CaseSpec]):
    req = RunRequest(
        run_id="validate",
        t=0,
        kind="submit",
        code=code,
        function=spec.function,
        cases=cases,
        limits=SUITE_LIMITS,
    )
    return await runner.run_tests("validate", req)


async def _brute_agrees(folder: Path, spec: ProblemSpec, runner: Runner) -> list[str]:
    """The reference matches brute.py on BRUTE_CASES generated inputs, compared like the hidden tests."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-I", "-c", _BRUTE_SCRIPT, str(folder), spec.function.name, str(BRUTE_CASES),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )  # fmt: skip
    try:
        async with asyncio.timeout(BRUTE_TIMEOUT_S):
            out, err = await proc.communicate()
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return [f"gen.py + brute.py took over {BRUTE_TIMEOUT_S:.0f} s"]
    if proc.returncode:
        return [f"gen.py or brute.py crashed: {err.decode(errors='replace')[-500:]}"]
    comparator = Counter(c.comparator for c in spec.tests_hidden).most_common(1)[0][0]
    cases = [
        CaseSpec(id=f"g{i}", args=args, expected=expected, comparator=comparator)
        for i, (args, expected) in enumerate(json.loads(out))
    ]
    result = await _run(runner, spec, spec.reference_solution, cases)
    bad = [c for c in result.cases if not c.passed]
    if result.compile_error or result.timed_out or bad:
        first = bad[0] if bad else None
        where = (
            f"{first.id}: args {first.input_repr}, brute {first.expected_repr}, got {first.actual_repr}"
            if first
            else ""
        )
        return [f"reference disagrees with brute.py on {len(bad)} of {len(cases)} random inputs ({where})"]
    return []


def _folders(args: argparse.Namespace) -> list[Path]:
    root = DEFAULT_ROOT / "_drafts" if args.drafts else DEFAULT_ROOT
    if args.all:
        return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")))
    return [root / slug for slug in args.slugs]


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m crucible.datatools.validate_problems")
    ap.add_argument("slugs", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--drafts", action="store_true", help="look in data/problems/_drafts/")
    args = ap.parse_args()
    if not args.all and not args.slugs:
        ap.error("name a slug or pass --all")
    from crucible.runner.local import LocalRunner  # dev tool: the problem bank is checked locally

    s = get_settings().model_copy(update={"RUNNER": "local", "ALLOW_LOCAL_RUNNER": True})
    reports = asyncio.run(validate(_folders(args), LocalRunner(s, isolate=False)))
    for r in reports:
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.slug}")
        for e in r.errors:
            print(f"      error: {e}")
        for w in r.warnings:
            print(f"      note:  {w}")
    passed = sum(r.ok for r in reports)
    print(f"\n{passed} of {len(reports)} problems pass")
    return 0 if passed == len(reports) else 1


if __name__ == "__main__":
    sys.exit(main())
