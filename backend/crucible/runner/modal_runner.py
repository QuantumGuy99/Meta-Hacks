"""ModalRunner: projects and attacks in Modal Sandboxes (PLAN §12).

One shared image built once; files are written into each running sandbox, so verify runs never rebuild an
image. ⚠️ VERIFY V7 against the live SDK (stdin API, readiness, egress): this module is covered only by the
`integration` test, which needs Modal credentials.
"""

from __future__ import annotations

import logging
import shlex
from collections.abc import AsyncIterator

from crucible.config import Settings, get_settings
from crucible.contracts.defense import Project
from crucible.runner.base import ProjectHandle, RunnerError

logger = logging.getLogger(__name__)

PROJECT_PACKAGES = ["fastapi", "uvicorn[standard]", "httpx", "aiosqlite", "flask"]
APP_DIR = "/work/app"
SANDBOX_TIMEOUT_S = 60 * 5  # covers boot + baseline/verify attack (≤ 30 s) + slack
READY_TIMEOUT_S = 20


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
        self._image = modal.Image.debian_slim(python_version="3.12").pip_install(*PROJECT_PACKAGES)
        self._app = None
        self._sandboxes: dict[str, object] = {}

    async def _get_app(self):
        if self._app is None:
            self._app = await self._modal.App.lookup.aio(
                self._settings.MODAL_APP_NAME, create_if_missing=True
            )
        return self._app

    async def start_project(self, project: Project, files: dict[str, str]) -> ProjectHandle:
        app = await self._get_app()
        sb = await self._modal.Sandbox.create.aio(app=app, image=self._image, timeout=SANDBOX_TIMEOUT_S)
        h = ProjectHandle(project_id=project.id, port=project.port, sandbox_id=sb.object_id)
        self._sandboxes[sb.object_id] = sb
        try:
            for rel, content in files.items():
                await self.put_file(h, f"app/{rel}", content)
            cmd = _uvicorn_cmd(project.entrypoint, project.port)
            await self._run(sb, f"cd {APP_DIR} && nohup {cmd} > /tmp/app.log 2>&1 &")
            await self._wait_ready(sb, project.port)
        except Exception:
            await self.stop_project(h)
            raise
        return h

    async def put_file(self, h: ProjectHandle, rel_path: str, content: str) -> None:
        if rel_path.startswith("/") or ".." in rel_path.split("/"):
            raise RunnerError(f"path escapes the work dir: {rel_path!r}")
        sb = self._sandbox(h)
        path = f"/work/{rel_path}"
        dirname = path.rsplit("/", 1)[0]
        p = await sb.exec.aio("sh", "-c", f"mkdir -p {shlex.quote(dirname)} && cat > {shlex.quote(path)}")
        p.stdin.write(content.encode())
        p.stdin.write_eof()
        await p.stdin.drain.aio()
        if await p.wait.aio():
            raise RunnerError(f"couldn't write {path} in the sandbox")

    async def stream_exec(self, h: ProjectHandle, argv: list[str], timeout_s: float) -> AsyncIterator[str]:
        sb = self._sandbox(h)
        cmd = " ".join(shlex.quote(a) for a in argv)
        p = await sb.exec.aio("sh", "-c", f"cd /work && {cmd} 2>&1", timeout=int(timeout_s))
        async for line in p.stdout:
            yield line.rstrip("\n")
        code = await p.wait.aio()
        if code == -1:  # Modal's code for an exec that hit its timeout
            raise RunnerError(f"exec timed out after {timeout_s:.0f} s")

    async def stop_project(self, h: ProjectHandle) -> None:
        sb = self._sandboxes.pop(h.sandbox_id or "", None)
        if sb is not None:
            try:
                await sb.terminate.aio()
            except Exception:
                logger.exception("couldn't terminate sandbox %s", h.sandbox_id)

    def _sandbox(self, h: ProjectHandle):
        sb = self._sandboxes.get(h.sandbox_id or "")
        if sb is None:
            raise RunnerError(f"no live sandbox for {h.project_id}")
        return sb

    async def _run(self, sb, script: str) -> None:
        p = await sb.exec.aio("sh", "-c", script)
        if await p.wait.aio():
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


def _uvicorn_cmd(entrypoint: str, port: int) -> str:
    parts = shlex.split(entrypoint)
    if not parts or parts[0] != "uvicorn":
        raise RunnerError(f"unsupported entrypoint {entrypoint!r}: only `uvicorn module:app ...` for now")
    args = [a for a in parts[1:] if not a.startswith("--port")]
    cleaned, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a in ("--host",):
            skip = True
            continue
        cleaned.append(a)
    return " ".join(["uvicorn", *map(shlex.quote, cleaned), "--host", "127.0.0.1", "--port", str(port)])
