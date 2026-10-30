"""validate_problems: the §13.1 quality bar fires on broken problems and passes the real bank."""

import json
import shutil
from pathlib import Path

import pytest

from crucible.coding.problems import DEFAULT_ROOT, load_problem
from crucible.datatools.validate_problems import check_problem, static_checks
from crucible.runner.local import LocalRunner

GOLD = DEFAULT_ROOT / "room-bookings"


def _copy(tmp_path: Path, edit=None, files: dict[str, str] | None = None) -> Path:
    d = tmp_path / GOLD.name
    shutil.copytree(GOLD, d)
    if edit:
        raw = json.loads((d / "problem.json").read_text())
        edit(raw)
        (d / "problem.json").write_text(json.dumps(raw))
    for name, content in (files or {}).items():
        (d / name).write_text(content)
    return d


def test_the_real_problem_passes_the_static_checks():
    assert static_checks(load_problem(GOLD))[0] == []


def test_a_hint_with_code_is_an_error(tmp_path):
    def edit(raw):
        raw["rubric"]["steps"][0]["hints"][2] = "Try this:\nbookings.sort()\nmerged = []"

    errors, _ = static_checks(load_problem(_copy(tmp_path, edit)))
    assert any("contains code" in e for e in errors)


def test_an_edge_case_without_a_test_is_an_error(tmp_path):
    def edit(raw):
        raw["rubric"]["edge_cases"].append({"id": "e99", "description": "untested"})

    errors, _ = static_checks(load_problem(_copy(tmp_path, edit)))
    assert "edge case e99 has no test (set edge_case_id on a hidden test)" in errors


def test_two_hints_instead_of_three_is_an_error(tmp_path):
    def edit(raw):
        raw["rubric"]["steps"][1]["hints"].pop()

    errors, _ = static_checks(load_problem(_copy(tmp_path, edit)))
    assert any("2 hints" in e for e in errors)


@pytest.mark.asyncio
async def test_the_gold_problem_passes_every_runtime_check(local_settings):
    report = await check_problem(GOLD, LocalRunner(local_settings))
    assert report.ok, report.errors


@pytest.mark.asyncio
async def test_a_wrong_reference_and_a_disagreeing_brute_are_caught(local_settings, tmp_path):
    wrong = "def merge_bookings(bookings):\n    return sorted(bookings)\n"
    report = await check_problem(_copy(tmp_path, files={"reference.py": wrong}), LocalRunner(local_settings))
    assert any(e.startswith("reference fails") for e in report.errors)
    assert any("disagrees with brute.py" in e for e in report.errors)


@pytest.mark.asyncio
async def test_a_starter_that_passes_is_an_error(local_settings, tmp_path):
    def edit(raw):
        raw["starter_code"] = (GOLD / "reference.py").read_text()

    report = await check_problem(_copy(tmp_path, edit), LocalRunner(local_settings))
    assert "starter code passes every test" in report.errors
