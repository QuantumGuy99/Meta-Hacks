"""Tests for coding/problems.py: loading problem folders and picking one."""

import json
import random
from pathlib import Path

import pytest

from crucible.coding.problems import ProblemBank, ProblemError
from crucible.contracts.common import Difficulty
from tests.factories import QUIET_STREAK_REFERENCE, write_quiet_streak


def test_loads_a_problem_with_its_sibling_files(tmp_path: Path) -> None:
    write_quiet_streak(tmp_path)
    bank = ProblemBank.load(tmp_path)
    spec = bank.get("quiet-streak")
    assert spec is not None and len(bank) == 1
    assert spec.reference_solution == QUIET_STREAK_REFERENCE
    assert spec.statement_md.startswith("A library's")


def test_drafts_and_missing_roots_are_ignored(tmp_path: Path) -> None:
    write_quiet_streak(tmp_path / "_drafts")
    assert len(ProblemBank.load(tmp_path)) == 0
    assert len(ProblemBank.load(tmp_path / "nowhere")) == 0


def test_a_bad_problem_fails_in_strict_mode_and_is_skipped_otherwise(tmp_path: Path) -> None:
    folder = write_quiet_streak(tmp_path)
    raw = json.loads((folder / "problem.json").read_text())
    del raw["rubric"]
    (folder / "problem.json").write_text(json.dumps(raw))
    with pytest.raises(ProblemError):
        ProblemBank.load(tmp_path)
    assert len(ProblemBank.load(tmp_path, strict=False)) == 0


def test_the_slug_must_match_the_folder(tmp_path: Path) -> None:
    folder = write_quiet_streak(tmp_path)
    folder.rename(tmp_path / "other-name")
    with pytest.raises(ProblemError):
        ProblemBank.load(tmp_path)


def test_pick_filters_by_difficulty_and_topic(tmp_path: Path) -> None:
    write_quiet_streak(tmp_path)
    bank = ProblemBank.load(tmp_path)
    rng = random.Random(0)
    assert bank.pick(Difficulty.EASY, "Arrays", rng) is not None
    assert bank.pick(Difficulty.HARD, None, rng) is None
    assert bank.pick(None, "graphs", rng) is None
