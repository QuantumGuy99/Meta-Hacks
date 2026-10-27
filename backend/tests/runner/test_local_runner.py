"""LocalRunner guards and the real thing: boot the fixture app, attack it, watch it break (PLAN §12)."""

import pytest

from crucible.config import Settings
from crucible.runner.base import RunnerError, uvicorn_args
from crucible.runner.local import LocalRunner


def test_refuses_without_explicit_opt_in():
    with pytest.raises(RunnerError):
        LocalRunner(Settings(_env_file=None, RUNNER="local", ALLOW_LOCAL_RUNNER=False))
    with pytest.raises(RunnerError):
        LocalRunner(Settings(_env_file=None, RUNNER="modal", ALLOW_LOCAL_RUNNER=True))


def test_host_and_port_are_rewritten():
    expected = ["app.main:app", "--host", "127.0.0.1", "--port", "5555"]
    assert uvicorn_args("uvicorn app.main:app --host 0.0.0.0 --port 8080", 5555) == expected
    assert uvicorn_args("uvicorn app.main:app --port=8080 --host=0.0.0.0", 5555) == expected
    assert uvicorn_args("uvicorn app.main:app", 5555) == expected
    with pytest.raises(RunnerError):
        uvicorn_args("python serve.py", 1)


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
