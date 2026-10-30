"""ModalRunner against real Modal (V7). Needs Modal credentials; uses a few cents of credit per run.

uv run pytest -m integration tests/runner/test_modal_runner.py
"""

import json

import pytest

from crucible.config import Settings
from crucible.contracts.coding import ProblemSpec
from crucible.defense.attack_writer import render_attack
from crucible.runner.modal_runner import ModalRunner
from tests.runner.test_problem_run import FIXTURE, REFERENCE, submit

pytestmark = pytest.mark.integration


async def test_project_boots_breaks_and_stops_in_a_sandbox(bank):
    settings = Settings(_env_file=None, DATABASE_URL="sqlite:///:memory:", RUNNER="modal")
    if not settings.has_modal:
        pytest.skip("no Modal credentials")
    runner = ModalRunner(settings)
    h = await runner.start_project(bank.project, bank.files)
    try:
        script = render_attack(bank.reference_attack.functions, port=h.port, concurrency=50, duration_s=3)
        await runner.put_file(h, "attack.py", script)
        lines = [line async for line in runner.stream_exec(h, ["python", "attack.py"], timeout_s=60)]
        probe = "import urllib.request as u\ntry:\n    u.urlopen('http://example.com', timeout=5)\n    print('EGRESS-OPEN')\nexcept Exception as e:\n    print('EGRESS-BLOCKED', type(e).__name__)"
        await runner.put_file(h, "egress.py", probe)
        egress = [line async for line in runner.stream_exec(h, ["python", "egress.py"], timeout_s=30)]
    finally:
        await runner.stop_project(h)
    done = [json.loads(x) for x in lines if x.startswith('{"done"')]
    metrics = [x for x in lines if x.startswith('{"t_ms"')]
    assert done, "\n".join(lines[-20:])
    assert metrics and done[0]["requests"] > 0 and done[0]["errors"] == 0
    assert done[0]["invariant_ok"] is False  # the race reproduces in the sandbox too
    assert any("EGRESS-BLOCKED" in x for x in egress), egress  # nothing leaves the sandbox (V7)


def _modal_settings() -> Settings:
    settings = Settings(_env_file=None, DATABASE_URL="sqlite:///:memory:", RUNNER="modal")
    if not settings.has_modal:
        pytest.skip("no Modal credentials")
    return settings


async def test_coding_runs_reuse_one_warm_sandbox_and_stop_runaway_code():
    """RUN-2: the contracts fixture problem in a session sandbox; the reference passes, the starter fails, an
    infinite loop is stopped, and every run reuses the one sandbox."""
    spec = ProblemSpec.model_validate(json.loads(FIXTURE.read_text()))
    runner = ModalRunner(_modal_settings())
    try:
        await runner.open_session("it-session")
        sandbox = runner._test_sandboxes["it-session"]
        ref = await runner.run_tests("it-session", submit(spec, REFERENCE))
        assert ref.compile_error is None and ref.passed == ref.total == 3, [c.error for c in ref.cases]
        starter = await runner.run_tests("it-session", submit(spec, spec.starter_code))
        assert starter.passed < starter.total
        looping = submit(
            spec, "def longest_quiet_streak(readings, threshold):\n    while True:\n        pass\n"
        )
        stuck = await runner.run_tests("it-session", looping)
        assert stuck.passed == 0 and (stuck.timed_out or any(c.error for c in stuck.cases))
        assert runner._test_sandboxes["it-session"] is sandbox
    finally:
        await runner.close_session("it-session")
    assert "it-session" not in runner._test_sandboxes


async def test_a_sample_boots_with_its_pinned_requirements(bank):
    runner = ModalRunner(_modal_settings())
    files = {**bank.files, "requirements.txt": "fastapi==0.115.6\npydantic==2.10.4\nuvicorn==0.32.1\n"}
    h = await runner.start_project(bank.project, files)
    try:
        await runner.put_file(h, "v.py", "import fastapi\nprint(fastapi.__version__)\n")
        lines = [line async for line in runner.stream_exec(h, ["python", "v.py"], timeout_s=30)]
    finally:
        await runner.stop_project(h)
    assert "0.115.6" in lines, lines
