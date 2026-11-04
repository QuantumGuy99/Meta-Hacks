"""COD-3 step 3: a coding session warms its runner sandbox at start and closes it at the end (PLAN §10.3).

With RUNNER=modal the first Run otherwise pays the sandbox cold start inside the 20 s run deadline
(coding/tests.py RUN_DEADLINE_S). The warm-up runs in the background, so it never delays the greeting,
and a runner that fails to warm is logged and ignored: Run still opens the sandbox lazily.
"""

import asyncio
from pathlib import Path

from crucible.coding.problems import ProblemBank
from crucible.coding.session import CodingMode
from crucible.contracts.common import Phase
from crucible.contracts.events import RunResult
from crucible.runner.base import RunRequest
from tests.factories import runtime, write_quiet_streak


class RecordingRunner:
    """A Runner that only records its session calls. `gate` can hold open_session open."""

    name = "recording"

    def __init__(self, *, fail_open: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_open = fail_open
        self.gate: asyncio.Event | None = None

    async def open_session(self, session_id: str) -> None:
        self.calls.append(("open", session_id))
        if self.gate is not None:
            await self.gate.wait()
        if self.fail_open:
            raise RuntimeError("no sandbox today")

    async def close_session(self, session_id: str) -> None:
        self.calls.append(("close", session_id))

    async def run_tests(self, session_id: str, req: RunRequest) -> RunResult:
        raise AssertionError("not used here")


async def started(tmp_path: Path, runner: RecordingRunner):
    write_quiet_streak(tmp_path)
    rt = runtime()
    rt.session.phase = Phase.SETUP
    rt.controller = CodingMode(ProblemBank.load(tmp_path), runner=runner, warm_up=False)()
    await rt.controller.on_start(rt)
    return rt


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def test_start_warms_the_sandbox_without_delaying_the_problem(tmp_path: Path) -> None:
    runner = RecordingRunner()
    runner.gate = asyncio.Event()
    rt = await started(tmp_path, runner)
    await settle()
    # on_start returned (the problem is presented) while the warm-up is still held open.
    assert rt.session.phase == Phase.CLARIFY
    assert runner.calls == [("open", rt.session.id)]
    runner.gate.set()
    await settle()


async def test_a_failed_warm_up_never_breaks_the_session(tmp_path: Path) -> None:
    runner = RecordingRunner(fail_open=True)
    rt = await started(tmp_path, runner)
    await settle()
    assert rt.session.phase == Phase.CLARIFY


async def test_ending_the_session_closes_the_sandbox_once(tmp_path: Path) -> None:
    runner = RecordingRunner()
    rt = await started(tmp_path, runner)
    await settle()
    await rt.end("wrap-up answered")
    await settle()
    await rt.controller.on_close(rt)
    assert runner.calls == [("open", rt.session.id), ("close", rt.session.id)]


async def test_closing_without_an_end_still_closes_the_sandbox(tmp_path: Path) -> None:
    runner = RecordingRunner()
    rt = await started(tmp_path, runner)
    await settle()
    await rt.controller.on_close(rt)
    assert runner.calls == [("open", rt.session.id), ("close", rt.session.id)]
