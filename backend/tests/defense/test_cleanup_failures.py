"""Cleanup after an attack can't crash a stage: a finished run stands, and a locked app log never raises.

On Windows the app's log stayed locked by an orphaned process, so `stop_project` raised PermissionError
out of `run_attack`. The stage crashed before any ChaosRun was recorded, which left the session in chaos
with nothing to retry.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crucible.contracts.events import TimelineKind
from crucible.defense.audit import audit_from_flaws
from crucible.defense.chaos import run_attack
from crucible.runner import local as local_runner
from crucible.runner.base import ProjectHandle


class CleanupFails:
    """A runner whose attack finishes (one metric, then the done line) but whose cleanup raises."""

    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    async def start_project(self, project, files):
        return ProjectHandle(project_id=project.id, port=9, workdir="unused")

    async def put_file(self, h, rel_path, content):
        return None

    async def stream_exec(self, h, argv, timeout_s):
        yield json.dumps(
            {
                "t_ms": 500,
                "in_flight": 3,
                "rps": 10,
                "p50_ms": 1,
                "p95_ms": 2,
                "p99_ms": 3,
                "errors": 0,
                "violations": 4,
            }
        )
        yield json.dumps(
            {"done": True, "invariant_ok": False, "violations": 4, "detail": "money vanished", "requests": 9}
        )

    async def stop_project(self, h):
        raise self.exc


@pytest.mark.asyncio
async def test_a_failed_cleanup_keeps_the_finished_attack(bank, sink):
    finding = next(f for f in audit_from_flaws(bank).findings if f.chaos is not None)
    run = await run_attack(
        CleanupFails(PermissionError(32, "The process cannot access the file")),
        bank.project,
        bank.files,
        finding,
        bank.reference_attack.functions,
        sink,
        kind="baseline",
    )

    assert run.verdict == "broke"  # the attack's own result, not an error and not an exception
    assert len(run.metrics) == 1
    assert TimelineKind.CHAOS_RUN.value in sink.kinds()
    assert any("couldn't stop the app cleanly" in json.dumps(e.payload) for e in sink.events)


@pytest.mark.asyncio
async def test_a_locked_log_is_retried_then_left_without_raising(tmp_path, monkeypatch, caplog):
    log = tmp_path / "app.log"
    log.write_text("x", encoding="utf-8")
    calls = {"n": 0}

    def locked(self, missing_ok=False):
        calls["n"] += 1
        raise PermissionError(32, "in use")

    monkeypatch.setattr(Path, "unlink", locked)
    monkeypatch.setattr(local_runner, "LOG_REMOVE_WAIT_S", 0)

    await local_runner._remove_log(log)  # doesn't raise

    assert calls["n"] == local_runner.LOG_REMOVE_TRIES
    assert "couldn't delete the app log" in caplog.text


@pytest.mark.asyncio
async def test_a_log_released_on_a_retry_is_deleted(tmp_path, monkeypatch):
    log = tmp_path / "app.log"
    log.write_text("x", encoding="utf-8")
    real_unlink = Path.unlink
    calls = {"n": 0}

    def released_on_second_try(self, missing_ok=False):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError(32, "in use")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", released_on_second_try)
    monkeypatch.setattr(local_runner, "LOG_REMOVE_WAIT_S", 0)

    await local_runner._remove_log(log)

    assert calls["n"] == 2
    assert not log.exists()
