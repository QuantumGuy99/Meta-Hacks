"""ModalRunner deadlines (PLAN §21): a stalled Modal call becomes a RunnerError, never a hung session.

No network: a fake `modal` module whose calls never return."""

import asyncio
from types import SimpleNamespace

import pytest

from crucible.runner import modal_runner
from crucible.runner.base import ProjectHandle, RunnerError
from crucible.runner.modal_runner import ModalRunner


async def _forever(*args, **kwargs):
    await asyncio.Event().wait()


def _runner(monkeypatch) -> ModalRunner:
    for name in ("LOOKUP_TIMEOUT_S", "CREATE_TIMEOUT_S", "FILE_TIMEOUT_S", "COMMAND_TIMEOUT_S"):
        monkeypatch.setattr(modal_runner, name, 0.05)
    r = ModalRunner.__new__(ModalRunner)
    r._settings = SimpleNamespace(MODAL_APP_NAME="crucible-test")
    image = SimpleNamespace()
    image.pip_install = lambda *pkgs: image  # project images derive from the base
    r._base = image
    r._images = {}
    r._test_sandboxes = {}
    r._session_locks = {}
    r._app = None
    r._sandboxes = {}
    r._modal = SimpleNamespace(
        App=SimpleNamespace(lookup=SimpleNamespace(aio=_forever)),
        Sandbox=SimpleNamespace(create=SimpleNamespace(aio=_forever)),
    )
    return r


@pytest.mark.asyncio
async def test_a_stalled_app_lookup_is_a_runner_error(monkeypatch, bank):
    with pytest.raises(RunnerError, match="app lookup"):
        await _runner(monkeypatch).start_project(bank.project, bank.files)


@pytest.mark.asyncio
async def test_a_stalled_sandbox_create_is_a_runner_error(monkeypatch, bank):
    r = _runner(monkeypatch)
    r._app = object()
    with pytest.raises(RunnerError, match="sandbox create"):
        await r.start_project(bank.project, bank.files)


@pytest.mark.asyncio
async def test_a_stalled_file_write_is_a_runner_error(monkeypatch):
    r = _runner(monkeypatch)
    r._sandboxes["sb1"] = SimpleNamespace(exec=SimpleNamespace(aio=_forever))
    h = ProjectHandle(project_id="p", port=8080, sandbox_id="sb1")
    with pytest.raises(RunnerError, match="file write"):
        await r.put_file(h, "attack.py", "print(1)")
