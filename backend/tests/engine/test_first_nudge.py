"""The IC1 path end to end (PLAN §4.2, §17): candidate activity → analyzer → policy → a nudge on screen.

Runs through the real API, hub and engine with the quiet-streak sample and a scripted model.
"""

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from crucible.coding.problems import ProblemBank
from crucible.coding.session import CodingMode
from crucible.contracts.common import Mode
from crucible.contracts.events import TimelineKind
from crucible.engine.api import router
from crucible.engine.hub import SessionHub
from crucible.engine.store import MemoryStore
from tests.factories import FakeModel, analysis, write_quiet_streak

DRAFT = "Before you go further, what should an empty list give you?"


def make_client(tmp_path: Path, model: FakeModel) -> TestClient:
    write_quiet_streak(tmp_path)
    app = FastAPI()
    app.include_router(router)
    modes = {Mode.CODING: CodingMode(ProblemBank.load(tmp_path))}
    app.state.hub = SessionHub(MemoryStore(), modes, model=model)
    return TestClient(app)


@pytest.fixture
def model() -> FakeModel:
    return FakeModel(analysis(text=DRAFT))


@pytest.fixture
def client(tmp_path: Path, model: FakeModel) -> Iterator[TestClient]:
    with make_client(tmp_path, model) as test_client:
        yield test_client


def receive_until(ws: Any, done: Callable[[dict[str, Any]], bool], limit: int = 30) -> dict[str, Any]:
    for _ in range(limit):
        message = ws.receive_json()
        if done(message):
            return message
    raise AssertionError("expected message never arrived")


def join(client: TestClient, **config: Any) -> tuple[str, Any]:
    response = client.post("/api/sessions", json={"mode": "coding", "problem_slug": "quiet-streak", **config})
    assert response.status_code == 201, response.text
    sid = response.json()["id"]
    return sid, client.websocket_connect(f"/ws/sessions/{sid}")


def wait_for(check: Callable[[], bool], timeout_s: float = 5) -> None:
    deadline = time.monotonic() + timeout_s
    while not check():
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting")
        time.sleep(0.02)


def kinds(client: TestClient, sid: str, kind: TimelineKind) -> list[Any]:
    runtime = client.app.state.hub.runtimes[sid]
    return client.portal.call(runtime.timeline.tail, [kind])


def test_session_uses_the_problems_time_limit(client: TestClient) -> None:
    response = client.post("/api/sessions", json={"mode": "coding", "problem_slug": "quiet-streak"})
    assert response.json()["time_limit_s"] == 20 * 60


def test_an_unknown_problem_is_a_bad_config(client: TestClient) -> None:
    response = client.post("/api/sessions", json={"mode": "coding", "problem_slug": "nope"})
    assert response.status_code == 400 and response.json()["error"]["code"] == "bad_config"


def test_a_missed_step_seen_twice_becomes_a_nudge(client: TestClient, model: FakeModel) -> None:
    _, socket = join(client)
    with socket as ws:
        receive_until(ws, lambda m: m["type"] == "session.state" and m["phase"] == "clarify")
        ws.send_json({"type": "chat.send", "text": "I'll loop over the readings."})
        notes = receive_until(ws, lambda m: m["type"] == "notes.update")
        assert [s["status"] for s in notes["steps"]] == ["not_started", "in_progress"]
        ws.send_json({"type": "chat.send", "text": "Then I'll track the best run."})
        message = receive_until(ws, lambda m: m["type"] == "interviewer.message")
    intervention = message["intervention"]
    assert intervention["text"] == DRAFT
    assert (intervention["trigger"], intervention["level"], intervention["step_id"]) == (
        "missed_step",
        "nudge",
        "s1",
    )
    assert len(model.calls) == 2
    assert "Quiet Streak" in model.calls[0][1]["content"]


def test_passive_mode_shows_nothing_but_records_the_nudge(client: TestClient) -> None:
    sid, socket = join(client, feedback="passive")
    with socket as ws:
        receive_until(ws, lambda m: m["type"] == "session.state" and m["phase"] == "clarify")
        ws.send_json({"type": "chat.send", "text": "I'll loop over the readings."})
        ws.send_json({"type": "chat.send", "text": "Then I'll track the best run."})
        wait_for(lambda: len(kinds(client, sid, TimelineKind.INTERVENTION)) == 1)
        ws.send_json({"type": "hello", "client_now_ms": 0})
        seen = []
        while not seen or seen[-1] != "session.state":
            seen.append(ws.receive_json()["type"])
    assert "interviewer.message" not in seen and "notes.update" not in seen
    assert kinds(client, sid, TimelineKind.INTERVENTION)[0].payload["suppressed"] is True


def test_a_model_failure_skips_the_tick_and_says_so(tmp_path: Path) -> None:
    with make_client(tmp_path, FakeModel(RuntimeError("model down"))) as client:
        sid, socket = join(client)
        with socket as ws:
            receive_until(ws, lambda m: m["type"] == "session.state" and m["phase"] == "clarify")
            ws.send_json({"type": "chat.send", "text": "hello?"})
            wait_for(lambda: len(kinds(client, sid, TimelineKind.SYSTEM)) == 1)
        note = kinds(client, sid, TimelineKind.SYSTEM)[0]
        assert "analysis skipped" in note.payload["message"]


def test_ending_the_session_stops_the_analyzer(client: TestClient, model: FakeModel) -> None:
    sid, socket = join(client)
    with socket as ws:
        receive_until(ws, lambda m: m["type"] == "session.state" and m["phase"] == "clarify")
        ws.send_json({"type": "session.end"})
        receive_until(ws, lambda m: m["type"] == "session.state" and m["phase"] == "ended")
    assert client.app.state.hub.runtimes[sid].context is None
