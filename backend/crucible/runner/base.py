"""Runner protocol: the only way untrusted code (projects, attack scripts) is executed (PLAN §12)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from crucible.contracts.defense import Project


class RunnerError(Exception):
    """The runner couldn't start or run something (boot failure, readiness timeout, missing credentials)."""


@dataclass(slots=True)
class ProjectHandle:
    project_id: str
    port: int
    sandbox_id: str | None = None  # Modal sandbox id; None for LocalRunner
    workdir: str | None = None  # LocalRunner temp dir; None for Modal


class Runner(Protocol):
    """Project half of the Runner protocol. run_tests / open_session (coding mode) land in RUN-1."""

    name: str

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
