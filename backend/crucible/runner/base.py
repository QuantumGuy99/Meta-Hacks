"""Runner protocol: the only way untrusted code (projects, attack scripts) is executed (PLAN §12)."""

from __future__ import annotations

import shlex
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import Field

from crucible.contracts.coding import CaseSpec, FunctionSig
from crucible.contracts.common import Strict
from crucible.contracts.defense import Project
from crucible.contracts.events import RunResult


class RunnerError(Exception):
    """The runner couldn't start or run something (boot failure, readiness timeout, missing credentials)."""


@dataclass(slots=True)
class ProjectHandle:
    project_id: str
    port: int
    sandbox_id: str | None = None  # Modal sandbox id; None for LocalRunner
    workdir: str | None = None  # LocalRunner temp dir; None for Modal


class RunLimits(Strict):
    per_test_s: float = 2.0
    total_s: float = 10.0
    stdout_bytes: int = 4096


class RunRequest(Strict):
    """Backend-internal (never on the WebSocket), so it lives here, not in contracts/ (PLAN §12)."""

    run_id: str
    t: int  # session time when Run/Submit was pressed
    kind: Literal["run", "submit"]
    code: str
    function: FunctionSig
    cases: list[CaseSpec]  # run: visible only; submit: visible + hidden
    hidden_case_ids: list[str] = Field(
        default_factory=list
    )  # marks CaseResult.visible; redaction is the caller's job (§10.3)
    limits: RunLimits = RunLimits()


class Runner(Protocol):
    """Every untrusted execution goes through here: tests (coding) and projects + attacks (defense)."""

    name: str

    async def open_session(self, session_id: str) -> None:
        """Warm a sandbox for a coding session (no-op for LocalRunner)."""
        ...

    async def run_tests(self, session_id: str, req: RunRequest) -> RunResult: ...

    async def close_session(self, session_id: str) -> None: ...

    async def start_project(self, project: Project, files: dict[str, str]) -> ProjectHandle:
        """Write the files, start the entrypoint and return once the port accepts connections."""
        ...

    async def put_file(self, h: ProjectHandle, rel_path: str, content: str) -> None:
        """Write one file into the project's work dir (used for attack.py)."""
        ...

    def stream_exec(self, h: ProjectHandle, argv: list[str], timeout_s: float) -> AsyncIterator[str]:
        """Run argv in the work dir (argv[0] == "python" means the runner's Python) and yield stdout lines.
        Raises RunnerError on timeout."""
        ...

    async def stop_project(self, h: ProjectHandle) -> None: ...


def uvicorn_args(entrypoint: str, port: int, host: str = "127.0.0.1") -> list[str]:
    """`uvicorn module:app [opts]` → its arguments with our host and port (whatever crucible.json said)."""
    parts = shlex.split(entrypoint)
    if not parts or parts[0] != "uvicorn":
        raise RunnerError(f"unsupported entrypoint {entrypoint!r}: only `uvicorn module:app ...` for now")
    out, skip = [], False
    for arg in parts[1:]:
        if skip:
            skip = False
        elif arg in ("--port", "--host"):
            skip = True
        elif not arg.startswith(("--port=", "--host=")):
            out.append(arg)
    return [*out, "--host", host, "--port", str(port)]
