"""Run and Submit for coding sessions (PLAN §10.3, COD-3).

Run executes the visible tests, Submit visible + hidden, always through the `Runner`. The full result goes
on the timeline (the analyzer and report need it); the browser gets `redact_run()`'s copy, so hidden inputs
and outputs never leave the backend.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

from crucible.contracts.coding import ProblemSpec
from crucible.contracts.events import CodeSnapshot, RunResult, TimelineKind
from crucible.contracts.ws import RunResultMsg
from crucible.engine.ids import new_id
from crucible.engine.timeline import redact_run
from crucible.runner.base import RunnerError, RunRequest

if TYPE_CHECKING:
    from crucible.engine.hub import SessionRuntime
    from crucible.runner.base import Runner

logger = logging.getLogger(__name__)

RUN_DEADLINE_S = 20  # PLAN §21 test run 10 s, plus the runner's own kill margin and process start-up


class RunService:
    """One run at a time per session. `runner` may be a factory, built on first use, so a misconfigured
    runner shows up as an error on Run instead of at startup."""

    def __init__(self, runner: Runner | Callable[[], Runner]) -> None:
        self._runner = runner
        self._lock = asyncio.Lock()

    @property
    def runner(self) -> Runner:
        if not hasattr(self._runner, "run_tests"):
            self._runner = self._runner()
        return self._runner

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    async def open_session(self, session_id: str) -> None:
        """Warm the session's sandbox (COD-3 step 3). The runner decides what that means; a lazy
        runner opens one on the first Run instead."""
        await self.runner.open_session(session_id)

    async def close_session(self, session_id: str) -> None:
        await self.runner.close_session(session_id)

    async def run(
        self,
        rt: SessionRuntime,
        spec: ProblemSpec,
        kind: Literal["run", "submit"],
        file: str,
        code: str,
    ) -> RunResult | None:
        """Record the exact code, run the tests, record the full result and send the redacted one."""
        connection = rt.sender  # whoever pressed Run hears about a failure; everyone sees results
        async with self._lock:
            if rt.code.code(file) != code:  # the browser's copy wins (§9.3), and the replay must match
                snapshot = CodeSnapshot(
                    t=rt.now_ms(), file=file, version=rt.code.version_by_file.get(file, 0), code=code
                )
                rt.code.apply_snapshot(snapshot)
                await rt.record(TimelineKind.SNAPSHOT, snapshot, t=snapshot.t)
            req = request(spec, kind, code, t=rt.now_ms())
            try:
                async with asyncio.timeout(RUN_DEADLINE_S):
                    result = await self.runner.run_tests(rt.session.id, req)
            except (RunnerError, TimeoutError) as exc:
                message = str(exc) or "the test run didn't finish in time"
                logger.warning("run failed in %s: %s", rt.session.id, message)
                await rt.note("warning", f"{kind} failed: {message}")
                if connection is not None:
                    await rt.error(
                        connection, "runner_unavailable", f"Couldn't run your code: {message}", retryable=True
                    )
                return None
            await rt.record(TimelineKind.RUN, result, t=result.t)
            await rt.broadcast(RunResultMsg(type="run.result", result=redact_run(result)))
            return result


def request(spec: ProblemSpec, kind: Literal["run", "submit"], code: str, *, t: int) -> RunRequest:
    hidden = spec.tests_hidden if kind == "submit" else []
    return RunRequest(
        run_id=new_id(),
        t=t,
        kind=kind,
        code=code,
        function=spec.function,
        cases=[*spec.tests_visible, *hidden],
        hidden_case_ids=[c.id for c in hidden],
    )


def all_passed(result: RunResult) -> bool:
    return result.compile_error is None and not result.timed_out and result.passed == result.total > 0
