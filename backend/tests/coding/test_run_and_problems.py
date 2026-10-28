"""COD-1 problem API and COD-3 Run/Submit, end to end through the hub with the real LocalRunner (PLAN §10.3)."""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from crucible.coding.api import router as problems_router
from crucible.coding.problems import ProblemBank
from crucible.coding.session import CodingMode
from crucible.config import Settings
from crucible.contracts.common import Mode
from crucible.contracts.events import TimelineKind
from crucible.engine.api import router
from crucible.engine.hub import SessionHub
from crucible.engine.store import MemoryStore
from crucible.runner.base import RunnerError
from crucible.runner.local import LocalRunner
from tests.factories import QUIET_STREAK_REFERENCE, write_quiet_streak

BUGGY = """\
def longest_quiet_streak(readings, threshold):
    best = cur = 0
    for r in readings:
        if r < threshold:
            cur += 1
        else:
            best = max(best, cur)
            cur = 0
    print(readings)
    return best
"""


@pytest.fixture
def local_settings() -> Settings:
    return Settings(
        _env_file=None,
        DATABASE_URL="sqlite:///:memory:",
        RUNNER="local",
        ALLOW_LOCAL_RUNNER=True,
        LOCAL_RUNNER_ISOLATE=False,
        MODEL_API_KEY="",
    )


def make_client(tmp_path: Path, runner: Any) -> TestClient:
    write_quiet_streak(tmp_path)
    bank = ProblemBank.load(tmp_path)
    app = FastAPI()
    app.include_router(router)
    app.include_router(problems_router)
    app.state.problems = bank
    app.state.hub = SessionHub(MemoryStore(), {Mode.CODING: CodingMode(bank, runner=runner)})
    return TestClient(app)


@pytest.fixture
def client(tmp_path: Path, local_settings: Settings) -> Iterator[TestClient]:
    with make_client(tmp_path, lambda: LocalRunner(local_settings)) as c:
        yield c


def receive_until(ws: Any, done: Callable[[dict[str, Any]], bool], limit: int = 40) -> dict[str, Any]:
    for _ in range(limit):
        message = ws.receive_json()
        if done(message):
            return message
    raise AssertionError("expected message never arrived")


def join(client: TestClient) -> tuple[str, Any]:
    sid = client.post("/api/sessions", json={"mode": "coding", "problem_slug": "quiet-streak"}).json()["id"]
    return sid, client.websocket_connect(f"/ws/sessions/{sid}")


def in_phase(phase: str) -> Callable[[dict[str, Any]], bool]:
    return lambda m: m["type"] == "session.state" and m["phase"] == phase


# --- COD-1: problem API -------------------------------------------------------------------------------------


def test_problems_are_listed_and_filtered(client: TestClient) -> None:
    assert [p["slug"] for p in client.get("/api/problems").json()] == ["quiet-streak"]
    assert client.get("/api/problems", params={"difficulty": "hard"}).json() == []
    assert len(client.get("/api/problems", params={"topic": "ARRAY"}).json()) == 1


def test_a_problem_never_carries_hidden_tests_rubric_or_reference(client: TestClient) -> None:
    body = client.get("/api/problems/quiet-streak").json()
    assert body["title"] == "Quiet Streak" and len(body["tests_visible"]) == 1
    assert not {"tests_hidden", "rubric", "reference_solution", "brute_force_solution"} & set(body)
    assert "best = max(best, cur)" not in str(body)


def test_an_unknown_problem_is_a_404_envelope(client: TestClient) -> None:
    response = client.get("/api/problems/nope")
    assert response.status_code == 404 and response.json()["error"]["code"] == "problem_not_found"


# --- COD-3: Run and Submit ----------------------------------------------------------------------------------


def test_run_executes_only_the_visible_tests(client: TestClient) -> None:
    _, socket = join(client)
    with socket as ws:
        receive_until(ws, in_phase("clarify"))
        ws.send_json({"type": "code.run", "file": "solution.py", "code": QUIET_STREAK_REFERENCE})
        result = receive_until(ws, lambda m: m["type"] == "run.result")["result"]
    assert (result["kind"], result["passed"], result["total"]) == ("run", 1, 1)
    assert all(c["visible"] for c in result["cases"])


def test_submit_hides_hidden_test_details_from_the_browser(client: TestClient) -> None:
    sid, socket = join(client)
    with socket as ws:
        receive_until(ws, in_phase("clarify"))
        ws.send_json({"type": "code.submit", "file": "solution.py", "code": BUGGY})
        result = receive_until(ws, lambda m: m["type"] == "run.result")["result"]
    hidden = [c for c in result["cases"] if not c["visible"]]
    assert hidden and all(c["input_repr"] is None and c["actual_repr"] is None for c in hidden)
    assert not all(c["passed"] for c in hidden)  # the trailing streak isn't counted
    assert result["stdout"] == ""  # printing the arguments must not reveal hidden inputs
    runtime = client.app.state.hub.runtimes[sid]
    stored = client.portal.call(runtime.timeline.tail, [TimelineKind.RUN])[0].payload
    assert any(
        c["input_repr"] for c in stored["cases"] if not c["visible"]
    )  # the full result stays server-side


def test_run_records_the_exact_code_it_ran(client: TestClient) -> None:
    sid, socket = join(client)
    with socket as ws:
        receive_until(ws, in_phase("clarify"))
        ws.send_json({"type": "code.run", "file": "solution.py", "code": QUIET_STREAK_REFERENCE})
        receive_until(ws, lambda m: m["type"] == "run.result")
    runtime = client.app.state.hub.runtimes[sid]
    assert runtime.code.code() == QUIET_STREAK_REFERENCE
    kinds = [e.kind for e in client.portal.call(runtime.timeline.tail)]
    assert kinds.index(TimelineKind.SNAPSHOT) < kinds.index(TimelineKind.RUN)


def test_a_passing_submit_while_coding_moves_to_wrap_up(client: TestClient) -> None:
    _, socket = join(client)
    with socket as ws:
        receive_until(ws, in_phase("clarify"))
        ws.send_json({"type": "phase.advance", "to": "coding"})
        receive_until(ws, in_phase("coding"))
        ws.send_json({"type": "code.submit", "file": "solution.py", "code": QUIET_STREAK_REFERENCE})
        result = receive_until(ws, lambda m: m["type"] == "run.result")["result"]
        assert result["passed"] == result["total"]
        receive_until(ws, in_phase("wrap_up"))


def test_a_runner_failure_tells_the_sender_and_leaves_a_note(tmp_path: Path) -> None:
    def broken() -> Any:
        raise RunnerError("LocalRunner refuses to start unless RUNNER=local and ALLOW_LOCAL_RUNNER=1")

    with make_client(tmp_path, broken) as client:
        sid, socket = join(client)
        with socket as ws:
            receive_until(ws, in_phase("clarify"))
            ws.send_json({"type": "code.run", "file": "solution.py", "code": "x = 1\n"})
            error = receive_until(ws, lambda m: m["type"] == "error")
        assert error["code"] == "runner_unavailable" and error["retryable"] is True
        runtime = client.app.state.hub.runtimes[sid]
        notes = client.portal.call(runtime.timeline.tail, [TimelineKind.SYSTEM])
        assert any("run failed" in n.payload["message"] for n in notes)


def test_a_session_without_a_runner_says_it_cannot_run(tmp_path: Path) -> None:
    with make_client(tmp_path, None) as client:
        _, socket = join(client)
        with socket as ws:
            receive_until(ws, in_phase("clarify"))
            ws.send_json({"type": "code.run", "file": "solution.py", "code": "x = 1\n"})
            assert receive_until(ws, lambda m: m["type"] == "error")["code"] == "cannot_run"
