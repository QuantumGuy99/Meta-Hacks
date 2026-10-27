"""ModalRunner against real Modal (V7). Needs Modal credentials; uses a few cents of credit per run.

uv run pytest -m integration tests/runner/test_modal_runner.py
"""

import json

import pytest

from crucible.config import Settings
from crucible.defense.attack_writer import render_attack
from crucible.runner.modal_runner import ModalRunner

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
    finally:
        await runner.stop_project(h)
    done = [json.loads(x) for x in lines if x.startswith('{"done"')]
    metrics = [x for x in lines if x.startswith('{"t_ms"')]
    assert done, "\n".join(lines[-20:])
    assert metrics and done[0]["requests"] > 0 and done[0]["errors"] == 0
    assert done[0]["invariant_ok"] is False  # the race reproduces in the sandbox too
