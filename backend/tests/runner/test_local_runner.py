"""LocalRunner guards and the real thing: boot the fixture app, attack it, watch it break (PLAN §12)."""

import pytest

from crucible.config import Settings
from crucible.runner.base import RunnerError
from crucible.runner.local import LocalRunner, _with_port


def test_refuses_without_explicit_opt_in():
    with pytest.raises(RunnerError):
        LocalRunner(Settings(_env_file=None, RUNNER="local", ALLOW_LOCAL_RUNNER=False))
    with pytest.raises(RunnerError):
        LocalRunner(Settings(_env_file=None, RUNNER="modal", ALLOW_LOCAL_RUNNER=True))


def test_port_is_rewritten():
    assert _with_port(["app.main:app", "--host", "127.0.0.1", "--port", "8080"], 5555) == [
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "5555",
    ]
    assert _with_port(["app.main:app", "--port=8080"], 1) == [
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "1",
    ]


async def test_rejects_path_escape(local_settings, bank):
    runner = LocalRunner(local_settings)
    h = await runner.start_project(bank.project, bank.files)
    try:
        with pytest.raises(RunnerError):
            await runner.put_file(h, "../../evil.py", "x")
    finally:
        await runner.stop_project(h)


async def test_boot_failure_is_reported(local_settings, bank):
    runner = LocalRunner(local_settings)
    broken = {**bank.files, "app/main.py": "this is not python"}
    with pytest.raises(RunnerError, match="exited during startup"):
        await runner.start_project(bank.project, broken)
