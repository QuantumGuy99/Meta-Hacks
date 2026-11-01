"""DEF-14: replay the race with two requests, narrate it, and show it only when it's honest."""

import pytest

from crucible.contracts.defense import ReplayNarrative, ReplayStep
from crucible.defense.audit import audit_from_flaws
from crucible.defense.replay import check_steps, race_replay, render_replay, reproduce
from crucible.runner.local import LocalRunner
from tests.defense.fixtures import FakeLLM


def _steps(*lanes: str) -> list[ReplayStep]:
    return [ReplayStep(lane=lane, action=f"step {i}", line=i + 1) for i, lane in enumerate(lanes)]


def test_the_replay_keeps_the_attack_bodies_and_the_loopback_guard(bank):
    script = render_replay(bank.reference_attack.functions, port=8080)
    assert "TRIES = 5" in script and "_send_loopback_only" in script
    assert "async def worker" not in script  # the load runner is gone: exactly two requests


def test_well_formed_steps_are_kept_and_lines_clamped():
    steps = check_steps([*_steps("A", "B", "A"), ReplayStep(lane="B", action="writes", line=999)], 50)
    assert steps is not None and len(steps) == 4 and steps[-1].line is None


@pytest.mark.parametrize("lanes", [("A", "A", "A", "A"), ("A", "B"), ("A", "B") * 7])
def test_steps_missing_a_lane_or_out_of_range_are_not_shown(lanes):
    assert check_steps(_steps(*lanes), 50) is None


def test_steps_with_code_are_dropped():
    code = ReplayStep(lane="A", action="balance = read()\nbalance = balance + 1", line=3)
    assert check_steps([*_steps("A", "B", "A"), code], 50) is None  # three left: too few to show


@pytest.mark.e2e
async def test_two_requests_reproduce_the_race_and_not_on_the_fix(bank, local_settings):
    runner = LocalRunner(local_settings)
    fn = bank.reference_attack.functions
    broken = await reproduce(runner, bank.project, bank.files, fn)
    assert broken.reproduced and broken.attempts <= 5 and [lane.lane for lane in broken.lanes] == ["A", "B"]
    fixed = await reproduce(runner, bank.project, bank.fixed_files, fn)
    assert not fixed.reproduced and fixed.attempts == 5


@pytest.mark.e2e
async def test_a_replay_is_built_only_with_good_steps(bank, local_settings, sink):
    runner = LocalRunner(local_settings)
    finding = audit_from_flaws(bank).findings[0]
    llm = FakeLLM()
    llm.push("replay", ReplayNarrative(steps=_steps("A", "B", "A", "B")))
    replay = await race_replay(
        finding, bank.project, bank.files, bank.reference_attack.functions, runner, llm, sink
    )
    assert replay is not None and replay.finding_id == finding.id and len(replay.steps) == 4
    assert "disappeared" in replay.detail or "appeared" in replay.detail

    llm.push("replay", ReplayNarrative(steps=_steps("A", "A", "A", "A")))  # one lane only: not shown
    assert (
        await race_replay(
            finding, bank.project, bank.files, bank.reference_attack.functions, runner, llm, sink
        )
        is None
    )
