"""Code execution: Modal sandboxes in production, LocalRunner for dev (PLAN §12)."""

from __future__ import annotations

from crucible.config import Settings, get_settings
from crucible.runner.base import ProjectHandle, Runner, RunnerError

__all__ = ["ProjectHandle", "Runner", "RunnerError", "make_runner"]


def make_runner(settings: Settings | None = None) -> Runner:
    """Pick the runner from settings. No silent fallback: misconfiguration is an error, not mock data."""
    s = settings or get_settings()
    if s.RUNNER == "local":
        from crucible.runner.local import LocalRunner

        return LocalRunner(s)
    from crucible.runner.modal_runner import ModalRunner

    return ModalRunner(s)
