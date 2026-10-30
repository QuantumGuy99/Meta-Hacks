"""ModalRunner: coding tests and Defense projects in Modal Sandboxes (PLAN §12).

Every sandbox runs with `block_network=True`, so nothing is installed at run time: the test harness and each
project's pinned requirements are baked into images, which `prebuild` builds at startup. Coding sessions get
one warm sandbox each (RUN-2); each Defense run gets its own. Covered by the `integration` tests, which need
Modal credentials.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import shlex
from collections.abc import AsyncIterator, Awaitable, Iterable

from crucible.config import Settings, get_settings
from crucible.contracts.defense import Project
from crucible.contracts.events import RunResult
from crucible.runner.base import ProjectHandle, RunnerError, RunRequest, stopped_run, uvicorn_args
from crucible.runner.harness import HARNESS_DIR

logger = logging.getLogger(__name__)

PROJECT_PACKAGES = ["fastapi", "uvicorn[standard]", "httpx", "aiosqlite", "flask"]
APP_DIR = "/work/app"
HARNESS_PATH = "/harness/run_tests.py"
SANDBOX_TIMEOUT_S = 60 * 5  # covers boot + baseline/verify attack (≤ 30 s) + slack
READY_TIMEOUT_S = 20
# A coding session's sandbox lives at most as long as the longest session, and stops after 10 idle minutes
# (a run counts as activity), so a session that ends without close_session can't run up the bill.
TEST_SANDBOX_TIMEOUT_S = 60 * 75
TEST_IDLE_TIMEOUT_S = 60 * 10
HARNESS_MARGIN_S = 3.0  # on top of the run's total_s, for process start-up and the kill

# Deadlines on every Modal call (PLAN §21, root rule 6): a stalled API turns into a RunnerError, which the
# chaos stage reports as an `error` run with a retry, instead of hanging the session's WebSocket.
LOOKUP_TIMEOUT_S = 30
CREATE_TIMEOUT_S = 90  # the first create can pull the image
BUILD_TIMEOUT_S = 300  # prebuild: an image that isn't cached yet installs its packages here
FILE_TIMEOUT_S = 20
COMMAND_TIMEOUT_S = 30
TERMINATE_TIMEOUT_S = 15
STREAM_SLACK_S = 15  # on top of the exec's own timeout
STDERR_TAIL_BYTES = 2000
MAX_REQUIREMENTS = 20
# Pinned or bare package names only: the line goes to pip at image build, so nothing else gets through.
_REQUIREMENT = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9_,-]+\])?((==|>=|<=|~=)[A-Za-z0-9.*+!_-]+)?$"
)
_RUN_HARNESS = f'd=$(mktemp -d) && cd "$d" && python -I {HARNESS_PATH}; rc=$?; cd / && rm -rf "$d"; exit $rc'


class ModalRunner:
    name = "modal"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        if not self._settings.has_modal:
            raise RunnerError(
                "Modal credentials missing: set MODAL_TOKEN_ID/MODAL_TOKEN_SECRET or run `modal token new`"
            )
        import modal  # imported lazily so the rest of the backend works without Modal configured

        self._modal = modal
        self._base = (
            modal.Image.debian_slim(python_version="3.12")
            .pip_install(*PROJECT_PACKAGES)
            .add_local_file(HARNESS_DIR / "run_tests.py", HARNESS_PATH, copy=True)
        )
        self._images: dict[tuple[str, ...], object] = {}
        self._app = None
        self._sandboxes: dict[str, object] = {}  # Defense projects, by sandbox id
        self._test_sandboxes: dict[str, object] = {}  # coding sessions, by session id
        self._session_locks: dict[str, asyncio.Lock] = {}

    async def prebuild(self, file_sets: Iterable[dict[str, str]]) -> None:
        """Build the test image and every project image now, so the first session doesn't wait minutes."""
        app = await self._get_app()
        images = [self._base, *(self._project_image(files) for files in file_sets)]
        for image in images:
            await _within(BUILD_TIMEOUT_S, image.build.aio(app), "image build")
        logger.info("modal: %d image(s) built", len(images))

    # --- coding: tests (RUN-2) ------------------------------------------------------------------------------

    async def open_session(self, session_id: str) -> None:
        """Warm the session's sandbox now, so the first Run doesn't pay for the start."""
        await self._test_sandbox(session_id)

    async def close_session(self, session_id: str) -> None:
        sb = self._test_sandboxes.pop(session_id, None)
        self._session_locks.pop(session_id, None)
        if sb is not None:
            await self._terminate(sb)

    async def run_tests(self, session_id: str, req: RunRequest) -> RunResult:
        """The harness in the session's sandbox, in a fresh temp dir per run. A sandbox that died (idle
        timeout, Modal restart) is replaced once."""
        payload = _payload(req)
        try:
            return await self._run_harness(await self._test_sandbox(session_id), req, payload)
        except self._modal.exception.Error as exc:
            self._test_sandboxes.pop(session_id, None)
            logger.warning("modal: test sandbox for %s is gone (%s); starting a new one", session_id, exc)
        try:
            return await self._run_harness(await self._test_sandbox(session_id), req, payload)
        except self._modal.exception.Error as exc:
            self._test_sandboxes.pop(session_id, None)
            raise RunnerError(f"the test sandbox failed twice: {exc}") from exc

    # --- defense: projects --------------------------------------------------------------------------------

    async def start_project(self, project: Project, files: dict[str, str]) -> ProjectHandle:
        # block_network: no traffic in or out of the sandbox; the app and the attack still talk over loopback.
        # Verified on real Modal (V7). The template's loopback-only client is the second layer.
        sb = await self._create(self._project_image(files), timeout_s=SANDBOX_TIMEOUT_S)
        h = ProjectHandle(project_id=project.id, port=project.port, sandbox_id=sb.object_id)
        self._sandboxes[sb.object_id] = sb
        try:
            for rel, content in files.items():
                await self.put_file(h, f"app/{rel}", content)
            cmd = _uvicorn_cmd(project.entrypoint, project.port)
            await self._run(sb, f"cd {APP_DIR} && nohup {cmd} > /tmp/app.log 2>&1 &")
            await _within(
                READY_TIMEOUT_S + COMMAND_TIMEOUT_S, self._wait_ready(sb, project.port), "readiness probe"
            )
        except Exception:
            await self.stop_project(h)
            raise
        return h

    async def put_file(self, h: ProjectHandle, rel_path: str, content: str) -> None:
        if rel_path.startswith("/") or ".." in rel_path.split("/"):
            raise RunnerError(f"path escapes the work dir: {rel_path!r}")
        await _within(
            FILE_TIMEOUT_S, self._write(self._sandbox(h), f"/work/{rel_path}", content), "file write"
        )

    async def stream_exec(self, h: ProjectHandle, argv: list[str], timeout_s: float) -> AsyncIterator[str]:
        sb = self._sandbox(h)
        cmd = " ".join(shlex.quote(a) for a in argv)
        p = await _within(
            COMMAND_TIMEOUT_S,
            sb.exec.aio("sh", "-c", f"cd /work && {cmd} 2>&1", timeout=math.ceil(timeout_s)),
            "exec",
        )
        # Modal's stream yields chunks, not lines: several JSON lines can arrive glued together, or one
        # can arrive split. Buffer and cut on newlines so callers always see whole lines.
        buffer = ""
        try:
            async with asyncio.timeout(timeout_s + STREAM_SLACK_S):
                async for chunk in p.stdout:
                    buffer += chunk
                    *complete, buffer = buffer.split("\n")
                    for line in complete:
                        yield line
                if buffer:
                    yield buffer
                code = await p.wait.aio()
        except TimeoutError as exc:
            raise RunnerError(f"exec output stalled past {timeout_s + STREAM_SLACK_S:.0f} s") from exc
        if code == -1:  # Modal's code for an exec that hit its timeout
            raise RunnerError(f"exec timed out after {timeout_s:.0f} s")

    async def stop_project(self, h: ProjectHandle) -> None:
        sb = self._sandboxes.pop(h.sandbox_id or "", None)
        if sb is not None:
            await self._terminate(sb)

    # --- internals ------------------------------------------------------------------------------------------

    async def _get_app(self):
        if self._app is None:
            self._app = await _within(
                LOOKUP_TIMEOUT_S,
                self._modal.App.lookup.aio(self._settings.MODAL_APP_NAME, create_if_missing=True),
                "app lookup",
            )
        return self._app

    async def _create(self, image, *, timeout_s: int, idle_timeout_s: int | None = None):
        app = await self._get_app()
        return await _within(
            CREATE_TIMEOUT_S,
            self._modal.Sandbox.create.aio(
                app=app, image=image, timeout=timeout_s, idle_timeout=idle_timeout_s, block_network=True
            ),
            "sandbox create",
        )

    async def _test_sandbox(self, session_id: str):
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:  # two quick Runs must not start two sandboxes
            sb = self._test_sandboxes.get(session_id)
            if sb is None:
                sb = await self._create(
                    self._base, timeout_s=TEST_SANDBOX_TIMEOUT_S, idle_timeout_s=TEST_IDLE_TIMEOUT_S
                )
                self._test_sandboxes[session_id] = sb
            return sb

    async def _run_harness(self, sb, req: RunRequest, payload: bytes) -> RunResult:
        budget_s = req.limits.total_s + HARNESS_MARGIN_S

        async def run() -> tuple[int, str, object]:
            p = await sb.exec.aio("sh", "-c", _RUN_HARNESS, timeout=math.ceil(budget_s))
            p.stdin.write(payload)
            p.stdin.write_eof()
            await p.stdin.drain.aio()
            out = await p.stdout.read.aio()
            return await p.wait.aio(), out, p

        try:
            code, out, p = await _within(budget_s + COMMAND_TIMEOUT_S, run(), "test run")
        except RunnerError:
            return stopped_run(req, "the run took too long and was stopped")
        if code == -1:
            return stopped_run(req, "the run took too long and was stopped")
        if code != 0 or not out:
            err = await _within(COMMAND_TIMEOUT_S, p.stderr.read.aio(), "stderr")
            tail = err[-STDERR_TAIL_BYTES:]
            return stopped_run(req, f"the test process crashed (exit {code}): {tail}".strip())
        return RunResult.model_validate(
            {**json.loads(out), "run_id": req.run_id, "t": req.t, "kind": req.kind}
        )

    def _project_image(self, files: dict[str, str]):
        requirements = parse_requirements(files.get("requirements.txt", ""))
        if requirements not in self._images:
            self._images[requirements] = self._base.pip_install(*requirements) if requirements else self._base
        return self._images[requirements]

    def _sandbox(self, h: ProjectHandle):
        sb = self._sandboxes.get(h.sandbox_id or "")
        if sb is None:
            raise RunnerError(f"no live sandbox for {h.project_id}")
        return sb

    async def _terminate(self, sb) -> None:
        try:
            await _within(TERMINATE_TIMEOUT_S, sb.terminate.aio(), "terminate")
        except Exception:  # the sandbox also stops on its own timeout; never fail the caller over this
            logger.exception("couldn't terminate sandbox %s", getattr(sb, "object_id", "?"))

    async def _write(self, sb, path: str, content: str) -> None:
        dirname = path.rsplit("/", 1)[0]
        p = await sb.exec.aio("sh", "-c", f"mkdir -p {shlex.quote(dirname)} && cat > {shlex.quote(path)}")
        p.stdin.write(content.encode())
        p.stdin.write_eof()
        await p.stdin.drain.aio()
        if await p.wait.aio():
            raise RunnerError(f"couldn't write {path} in the sandbox")

    async def _run(self, sb, script: str) -> None:
        async def run() -> int:
            p = await sb.exec.aio("sh", "-c", script)
            return await p.wait.aio()

        if await _within(COMMAND_TIMEOUT_S, run(), "command"):
            raise RunnerError(f"sandbox command failed: {script[:120]}")

    async def _wait_ready(self, sb, port: int) -> None:
        probe = (
            "import socket,time\n"
            f"end=time.time()+{READY_TIMEOUT_S}\n"
            "while time.time()<end:\n"
            "    try:\n"
            f"        socket.create_connection(('127.0.0.1',{port}),0.5).close(); raise SystemExit(0)\n"
            "    except OSError: time.sleep(0.2)\n"
            "raise SystemExit(1)\n"
        )
        p = await sb.exec.aio("python", "-c", probe)
        if await p.wait.aio():
            log = await sb.exec.aio("sh", "-c", "tail -c 2000 /tmp/app.log")
            tail = await log.stdout.read.aio()
            raise RunnerError(f"app didn't open port {port} within {READY_TIMEOUT_S} s: {tail}")


def parse_requirements(text: str) -> tuple[str, ...]:
    """A project's requirements.txt → pip arguments for its image. Comments and blank lines are skipped;
    anything that isn't a plain (optionally pinned) package name is rejected."""
    lines = [line.split("#", 1)[0].strip() for line in text.splitlines()]
    reqs = tuple(sorted({line for line in lines if line}))
    if len(reqs) > MAX_REQUIREMENTS:
        raise RunnerError(f"requirements.txt lists {len(reqs)} packages (limit {MAX_REQUIREMENTS})")
    bad = [r for r in reqs if not _REQUIREMENT.match(r)]
    if bad:
        raise RunnerError(f"requirements.txt has lines we can't install: {bad[:3]}")
    return reqs


def _payload(req: RunRequest) -> bytes:
    return json.dumps(
        {
            "code": req.code,
            "function": req.function.model_dump(),
            "cases": [c.model_dump(mode="json") for c in req.cases],
            "limits": req.limits.model_dump(),
            "hidden_case_ids": req.hidden_case_ids,
        }
    ).encode()


async def _within[R](seconds: float, call: Awaitable[R], what: str) -> R:
    try:
        async with asyncio.timeout(seconds):
            return await call
    except TimeoutError as exc:
        raise RunnerError(f"Modal didn't answer within {seconds:.0f} s ({what})") from exc


def _uvicorn_cmd(entrypoint: str, port: int) -> str:
    return " ".join(["uvicorn", *map(shlex.quote, uvicorn_args(entrypoint, port))])
