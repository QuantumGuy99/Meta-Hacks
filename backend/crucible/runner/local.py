"""LocalRunner: runs projects as local subprocesses in a temp dir. Dev and tests only (PLAN §12)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import socket
import sys
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from crucible.config import Settings, get_settings
from crucible.contracts.defense import Project
from crucible.contracts.events import RunResult
from crucible.runner.base import ProjectHandle, RunnerError, RunRequest, stopped_run, uvicorn_args
from crucible.runner.harness import HARNESS_DIR

logger = logging.getLogger(__name__)

READY_TIMEOUT_S = 15.0
HARNESS_MARGIN_S = 3.0
STDERR_TAIL_BYTES = 2000
LOG_REMOVE_TRIES = 10  # the app's log, after stopping it (a dying process can hold it for a moment)
LOG_REMOVE_WAIT_S = 0.2


class LocalRunner:
    name = "local"

    def __init__(self, settings: Settings | None = None, *, isolate: bool | None = None) -> None:
        self._settings = settings or get_settings()
        if not (self._settings.RUNNER == "local" and self._settings.ALLOW_LOCAL_RUNNER):
            raise RunnerError("LocalRunner refuses to start unless RUNNER=local and ALLOW_LOCAL_RUNNER=1")
        self._isolate = self._settings.LOCAL_RUNNER_ISOLATE if isolate is None else isolate
        if self._isolate and shutil.which("uv") is None:
            raise RunnerError("LOCAL_RUNNER_ISOLATE=1 needs `uv` on PATH")
        self._procs: dict[str, asyncio.subprocess.Process] = {}
        self._logs: dict[str, Path] = {}

    # --- coding: tests ----------------------------------------------------------------------------------

    async def open_session(self, session_id: str) -> None:
        return None  # nothing to warm locally

    async def close_session(self, session_id: str) -> None:
        return None

    async def run_tests(self, session_id: str, req: RunRequest) -> RunResult:
        """The harness in a fresh subprocess (its own temp dir, no project files), killed after
        total_s + a margin if the candidate's code wedges where the per-test timer can't reach."""
        payload = json.dumps(
            {
                "code": req.code,
                "function": req.function.model_dump(),
                "cases": [c.model_dump(mode="json") for c in req.cases],
                "limits": req.limits.model_dump(),
                "hidden_case_ids": req.hidden_case_ids,
            }
        ).encode()
        workdir = await asyncio.to_thread(tempfile.mkdtemp, prefix="crucible-tests-")
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            str(HARNESS_DIR / "run_tests.py"),
            cwd=workdir,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            async with asyncio.timeout(req.limits.total_s + HARNESS_MARGIN_S):
                out, err = await proc.communicate(payload)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return stopped_run(req, "the run took too long and was stopped")
        finally:
            await asyncio.to_thread(shutil.rmtree, workdir, True)
        if proc.returncode != 0 or not out:
            tail = err.decode(errors="replace")[-STDERR_TAIL_BYTES:]
            return stopped_run(req, f"the test process crashed (exit {proc.returncode}): {tail}".strip())
        return RunResult.model_validate(
            {**json.loads(out), "run_id": req.run_id, "t": req.t, "kind": req.kind}
        )

    # --- defense: projects --------------------------------------------------------------------------------

    async def start_project(self, project: Project, files: dict[str, str]) -> ProjectHandle:
        workdir = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix=f"crucible-{project.id}-"))
        await asyncio.to_thread(_write_all, workdir, files)
        port = _free_port()
        argv = self._entrypoint_argv(project.entrypoint, port, workdir)
        # App logs go to a file outside the work dir: a never-drained PIPE fills up under load (uvicorn logs
        # every request) and freezes the app mid-attack.
        fd, log_name = tempfile.mkstemp(prefix=f"crucible-{project.id}-", suffix=".log")
        os.close(fd)
        log_path = Path(log_name)
        log = await asyncio.to_thread(log_path.open, "wb")
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=workdir,
                stdout=log,
                stderr=asyncio.subprocess.STDOUT,
            )
        finally:
            log.close()  # the child keeps its own copy of the descriptor
        h = ProjectHandle(project_id=project.id, port=port, workdir=str(workdir))
        self._procs[h.workdir] = proc
        self._logs[h.workdir] = log_path
        try:
            await _wait_ready(port, proc, log_path, READY_TIMEOUT_S if not self._isolate else 120.0)
        except RunnerError:
            await self.stop_project(h)
            raise
        logger.info("project %s up on :%d (%s)", project.id, port, workdir)
        return h

    async def put_file(self, h: ProjectHandle, rel_path: str, content: str) -> None:
        await asyncio.to_thread(_safe_write, Path(_workdir(h)), rel_path, content)

    async def stream_exec(self, h: ProjectHandle, argv: list[str], timeout_s: float) -> AsyncIterator[str]:
        if argv and argv[0] == "python":
            argv = [sys.executable, *argv[1:]]
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=_workdir(h),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert proc.stdout is not None
        try:
            async with asyncio.timeout(timeout_s):
                async for raw in proc.stdout:
                    yield raw.decode(errors="replace").rstrip("\n")
                await proc.wait()
        except TimeoutError as exc:
            raise RunnerError(f"exec timed out after {timeout_s:.0f} s") from exc
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
        if proc.returncode:
            logger.warning("exec %s exited with code %s", argv[:2], proc.returncode)

    async def stop_project(self, h: ProjectHandle) -> None:
        proc = self._procs.pop(h.workdir or "", None)
        if proc and proc.returncode is None:
            await _stop_tree(proc)
        log_path = self._logs.pop(h.workdir or "", None)
        if log_path:
            await _remove_log(log_path)
        if h.workdir:
            await asyncio.to_thread(shutil.rmtree, h.workdir, True)

    def _entrypoint_argv(self, entrypoint: str, port: int, workdir: Path) -> list[str]:
        args = uvicorn_args(entrypoint, port)
        if self._isolate:
            req = workdir / "requirements.txt"
            with_req = ["--with-requirements", str(req)] if req.exists() else []
            return [
                "uv",
                "run",
                "--no-project",
                "--python",
                "3.12",
                *with_req,
                "--with",
                "uvicorn",
                "python",
                "-m",
                "uvicorn",
                *args,
            ]
        return [sys.executable, "-m", "uvicorn", *args]


def _write_all(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        _safe_write(root, rel, content)


def _safe_write(root: Path, rel: str, content: str) -> None:
    target = (root / rel).resolve()
    if not target.is_relative_to(root.resolve()):
        raise RunnerError(f"path escapes the work dir: {rel!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _workdir(h: ProjectHandle) -> str:
    if not h.workdir:
        raise RunnerError("LocalRunner handle has no workdir")
    return h.workdir


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _stop_tree(proc: asyncio.subprocess.Process) -> None:
    """Stop the app and everything it started.

    With LOCAL_RUNNER_ISOLATE the process is `uv run`, which starts the app as a child. On Windows,
    terminate() ends only `uv`, and the orphaned app keeps the port and the log file open, so the log
    can't be deleted (WinError 32). taskkill /T ends the whole tree. Elsewhere terminate() reaches the app.
    """
    if os.name == "nt":
        with contextlib.suppress(OSError):
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(proc.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.wait()
    else:
        proc.terminate()
    try:
        async with asyncio.timeout(5):
            await proc.wait()
    except TimeoutError:
        proc.kill()
        await proc.wait()


async def _remove_log(log_path: Path) -> None:
    """Delete the app's log. A file a dying process still holds gets a moment to be released; one that
    stays locked is left in the temp dir, since a leftover temp file must never fail a stage."""
    for attempt in range(LOG_REMOVE_TRIES):
        try:
            await asyncio.to_thread(log_path.unlink, missing_ok=True)
            return
        except PermissionError:
            if attempt + 1 < LOG_REMOVE_TRIES:
                await asyncio.sleep(LOG_REMOVE_WAIT_S)
        except OSError:
            break
    logger.warning("couldn't delete the app log %s; leaving it in the temp dir", log_path)


async def _wait_ready(port: int, proc: asyncio.subprocess.Process, log_path: Path, timeout_s: float) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while loop.time() < deadline:
        if proc.returncode is not None:
            err = (await asyncio.to_thread(log_path.read_bytes))[-STDERR_TAIL_BYTES:].decode(errors="replace")
            raise RunnerError(f"app exited during startup (code {proc.returncode}): {err}")
        with contextlib.suppress(OSError):
            _, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return
        await asyncio.sleep(0.1)
    raise RunnerError(f"app didn't open port {port} within {timeout_s:.0f} s")
