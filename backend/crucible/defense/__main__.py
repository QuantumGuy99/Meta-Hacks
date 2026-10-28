"""Run the whole Defense pipeline from the terminal (standalone, no frontend or engine needed).

    uv run python -m crucible.defense --project bank-transfer-min --apps-dir tests/fixtures/apps \
        --answer "The balances are read before the await ..." --duration 5
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from crucible.config import get_settings
from crucible.defense.model_client import WrapperModelClient
from crucible.defense.pipeline import DefensePipeline, run_scripted
from crucible.defense.ports import MemorySink
from crucible.defense.projects import load_samples
from crucible.runner import RunnerError, make_runner


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m crucible.defense")
    ap.add_argument("--project", required=True)
    ap.add_argument("--answer", required=True, help="grill answer for every broken finding")
    ap.add_argument("--apps-dir", type=Path, default=None, help="extra sample-app directory")
    ap.add_argument("--duration", type=int, default=None, help="override attack duration (s)")
    ap.add_argument("--no-fix", action="store_true", help="verify the ORIGINAL code (should fail)")
    ap.add_argument("--runner", choices=["local", "modal"], default=None)
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)

    s = get_settings()
    if args.runner:
        s = s.model_copy(update={"RUNNER": args.runner, "ALLOW_LOCAL_RUNNER": args.runner == "local"})
    samples = load_samples(s.DEFENSE_APPS_DIR, s.DEFENSE_EXTRA_APPS_DIR, args.apps_dir)
    sample = samples.get(args.project)
    if sample is None:
        print(f"unknown project {args.project!r}; have: {sorted(samples)}", file=sys.stderr)
        return 2
    try:
        runner = make_runner(s)
    except RunnerError as exc:
        print(f"runner: {exc}", file=sys.stderr)
        return 2
    pipeline = DefensePipeline(
        sample, runner, WrapperModelClient(), MemorySink(echo=True), duration_override_s=args.duration
    )
    fixed = None if args.no_fix else (sample.fixed_files or {})
    verdict = asyncio.run(run_scripted(pipeline, args.answer, fixed))
    print("\nMERGE GATE:", "PASS" if verdict.passed else "FAIL")
    for r in verdict.reasons:
        print("  -", r)
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    sys.exit(main())
