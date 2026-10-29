"""The coding report extras (COD-5): step statuses and approach from the analyses (grading: test_complexity.py)."""

from pathlib import Path

import pytest

from crucible.coding.problems import ProblemBank
from crucible.coding.session import CodingController, CodingMode
from crucible.contracts.coding import Analysis
from crucible.contracts.events import TimelineKind
from tests.factories import analysis, runtime, write_quiet_streak


def controller(tmp_path: Path) -> CodingController:
    write_quiet_streak(tmp_path)
    return CodingMode(ProblemBank.load(tmp_path))()


def analysed(s1: str = "not_started", s2: str = "in_progress", **fields: object) -> Analysis:
    return Analysis.model_validate({**analysis(s1, s2, proposal=False), **fields})


@pytest.mark.asyncio
async def test_the_latest_statuses_and_the_named_approach(tmp_path: Path) -> None:
    rt = runtime()
    rt.timeline.append(TimelineKind.ANALYSIS, analysed(chosen_approach="brute force"))
    rt.timeline.append(TimelineKind.ANALYSIS, analysed(s1="done", s2="done", chosen_approach="single pass"))
    extra = await controller(tmp_path).report_extra(rt)
    assert [s.status for s in extra.steps] == ["done", "done"]
    assert (extra.approach, extra.problem_slug) == ("single pass", "quiet-streak")


@pytest.mark.asyncio
async def test_without_a_named_approach_the_stated_plan_is_used(tmp_path: Path) -> None:
    rt = runtime()
    rt.timeline.append(
        TimelineKind.ANALYSIS, analysed(chosen_approach=None, stated_plan="Walk once, count jumps.")
    )
    rt.timeline.append(TimelineKind.ANALYSIS, analysed(chosen_approach=None, stated_plan=None))
    extra = await controller(tmp_path).report_extra(rt)
    assert extra.approach == "Walk once, count jumps."


@pytest.mark.asyncio
async def test_no_analyses_means_no_steps_or_approach(tmp_path: Path) -> None:
    extra = await controller(tmp_path).report_extra(runtime())
    assert (extra.steps, extra.approach) == ([], None)
