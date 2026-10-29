"""validate_apps: static checks fire on bad ground truth; the attack must break the original and hold the fix."""

import dataclasses

import pytest

from crucible.datatools.validate_apps import check_app, static_checks
from crucible.runner.local import LocalRunner


def test_the_fixture_app_passes_the_static_checks(bank):
    assert static_checks(bank, None) == []


def test_lines_outside_the_file_are_an_error(bank):
    flaws = [{**bank.flaws[0], "line_start": 900, "line_end": 901}]
    errors = static_checks(dataclasses.replace(bank, flaws=flaws), None)
    assert any("outside" in e for e in errors)


def test_a_missing_reference_fix_is_an_error(bank):
    errors = static_checks(dataclasses.replace(bank, fixed_files=None), None)
    assert "no reference fix (fix.patch or fixed/)" in errors


@pytest.mark.asyncio
async def test_the_fixture_app_breaks_then_holds(bank, local_settings):
    report = await check_app(bank, None, LocalRunner(local_settings), runs=1, duration_s=2)
    assert report.ok, report.errors
    assert [line.split(":")[0] for line in report.runs] == ["f1 baseline #1", "f1 verify #1"]


@pytest.mark.asyncio
async def test_a_fix_that_changes_nothing_fails(bank, local_settings):
    unfixed = dataclasses.replace(bank, fixed_files=dict(bank.files))
    report = await check_app(unfixed, None, LocalRunner(local_settings), runs=1, duration_s=2)
    assert any("reference fix should have held but broke" in e for e in report.errors)
