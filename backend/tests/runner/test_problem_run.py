"""RUN-1's "done when": LocalRunner runs a real problem end to end (PLAN §16). Until Sharvil's gold problems
land, this uses the contracts fixture problem; the same shape `validate_problems` will check per problem."""

import json
from pathlib import Path

from crucible.contracts.coding import ProblemSpec
from crucible.runner.base import RunRequest
from crucible.runner.local import LocalRunner

FIXTURE = Path(__file__).parents[1] / "fixtures" / "problem_spec.json"
REFERENCE = """\
def longest_quiet_streak(readings: list[int], threshold: int) -> int:
    best = run = 0
    for r in readings:
        run = run + 1 if r < threshold else 0
        best = max(best, run)
    return best
"""


def submit(spec: ProblemSpec, code: str) -> RunRequest:
    cases = [*spec.tests_visible, *spec.tests_hidden]
    return RunRequest(
        run_id="r",
        t=0,
        kind="submit",
        code=code,
        function=spec.function,
        cases=cases,
        hidden_case_ids=[c.id for c in spec.tests_hidden],
    )


async def test_reference_passes_every_case_and_the_starter_fails(local_settings):
    spec = ProblemSpec.model_validate(json.loads(FIXTURE.read_text()))
    runner = LocalRunner(local_settings)

    ref = await runner.run_tests("s", submit(spec, REFERENCE))
    assert ref.compile_error is None and ref.passed == ref.total == 3, [c.error for c in ref.cases]
    assert [c.visible for c in ref.cases] == [True, False, False]

    starter = await runner.run_tests("s", submit(spec, spec.starter_code))
    assert starter.passed < starter.total  # a starter that already passes is a broken problem
