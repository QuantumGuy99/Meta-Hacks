"""End-to-end tests for the session API and WebSocket hub (PLAN §8, §9.1), with an in-memory store."""

import json
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from crucible.coding.problems import ProblemBank
from crucible.coding.session import CodingMode
from crucible.contracts.common import Mode
from crucible.contracts.events import TimelineKind
from crucible.contracts.ws import ChatSend, SessionState
from crucible.engine.api import SESSION_NOT_FOUND_CLOSE, router
from crucible.engine.hub import SessionHub
from crucible.engine.store import MemoryStore

IDLE_TTL_S = 0.1


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router)
    app.state.hub = SessionHub(
        MemoryStore(), {Mode.CODING: CodingMode(ProblemBank([]))}, idle_ttl_s=IDLE_TTL_S
    )
    with TestClient(app) as test_client:
        yield test_client


def hub(client: TestClient) -> SessionHub:
    return client.app.state.hub


def new_session(client: TestClient, **config: Any) -> dict[str, Any]:
    response = client.post("/api/sessions", json={"mode": "coding", "difficulty": "easy", **config})
    assert response.status_code == 201, response.text
    return response.json()


def receive_until(ws: Any, done: Callable[[dict[str, Any]], bool], limit: int = 20) -> dict[str, Any]:
    for _ in range(limit):
        message = ws.receive_json()
        if done(message):
            return message
    raise AssertionError("expected message never arrived")


def state_in(phase: str) -> Callable[[dict[str, Any]], bool]:
    return lambda m: m["type"] == "session.state" and m["phase"] == phase


def sync(ws: Any) -> dict[str, Any]:
    """Messages are handled in order, so a hello reply means everything sent before it is done."""
    ws.send_json({"type": "hello", "client_now_ms": 0})
    return receive_until(ws, lambda m: m["type"] == "session.state")


def edit(
    t: int, version: int, offset: int, text: str, kind: str = "change", length: int = 0
) -> dict[str, Any]:
    return {
        "t": t,
        "file": "solution.py",
        "version": version,
        "kind": kind,
        "changes": [{"range_offset": offset, "range_length": length, "text": text}],
    }


def test_create_session_uses_the_difficulty_time_limit(client: TestClient) -> None:
    session = new_session(client)
    assert session["phase"] == "setup"
    assert session["time_limit_s"] == 20 * 60
    assert len(session["id"]) == 12 and session["started_at"] is None


def test_unregistered_mode_returns_an_api_error(client: TestClient) -> None:
    response = client.post("/api/sessions", json={"mode": "defense", "project_id": "bank-transfer"})
    assert response.status_code == 400
    assert response.json() == {
        "error": {"code": "mode_unavailable", "message": "defense sessions aren't available yet"}
    }


def test_unknown_session_is_404_with_the_error_shape(client: TestClient) -> None:
    response = client.get("/api/sessions/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "session_not_found"


def test_unknown_session_socket_is_closed(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc, client.websocket_connect("/ws/sessions/nope") as ws:
        ws.receive_json()
    assert exc.value.code == SESSION_NOT_FOUND_CLOSE


def test_first_connect_starts_the_session_and_hello_returns_state(client: TestClient) -> None:
    session = new_session(client)
    with client.websocket_connect(f"/ws/sessions/{session['id']}") as ws:
        receive_until(ws, state_in("clarify"))
        state = sync(ws)
    assert state["phase"] == "clarify"
    assert state["session"]["started_at"] is not None
    assert 0 < state["remaining_s"] <= 20 * 60
    assert state["interviewer_state"] == "idle"


def test_edits_come_back_from_the_timeline_in_order(client: TestClient) -> None:
    session = new_session(client)
    sid = session["id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        receive_until(ws, state_in("clarify"))
        ws.send_json(
            {
                "type": "editor.events",
                "events": [edit(1000, 2, 0, "def f():\n"), edit(1500, 3, 9, "    pass\n")],
            }
        )
        ws.send_json(
            {
                "type": "editor.snapshot",
                "snapshot": {"t": 1600, "file": "solution.py", "version": 3, "code": "def f():\n    pass\n"},
            }
        )
        sync(ws)
        assert hub(client).runtimes[sid].code.code() == "def f():\n    pass\n"
    events = client.get(f"/api/sessions/{sid}/timeline").json()
    # phase → intro, the intro line (intervention + transcript), phase → clarify, then the edits
    assert [e["kind"] for e in events] == [
        "phase",
        "intervention",
        "transcript",
        "phase",
        "editor",
        "editor",
        "snapshot",
    ]
    assert [e["seq"] for e in events] == list(range(1, 8))
    assert [e["t"] for e in events[4:]] == [1000, 1500, 1600]
    assert events[5]["payload"]["changes"][0]["text"] == "    pass\n"


def test_a_bad_message_gets_an_error_and_the_socket_stays_open(client: TestClient) -> None:
    session = new_session(client)
    with client.websocket_connect(f"/ws/sessions/{session['id']}") as ws:
        receive_until(ws, state_in("clarify"))
        ws.send_json({"type": "editor.events", "events": [{"t": "soon"}]})
        error = receive_until(ws, lambda m: m["type"] == "error")
        assert error["code"] == "bad_message" and error["retryable"] is False
        assert sync(ws)["phase"] == "clarify"


def test_candidate_can_only_start_coding_and_finish(client: TestClient) -> None:
    session = new_session(client)
    with client.websocket_connect(f"/ws/sessions/{session['id']}") as ws:
        receive_until(ws, state_in("clarify"))
        ws.send_json({"type": "phase.advance", "to": "ended"})
        assert receive_until(ws, lambda m: m["type"] == "error")["code"] == "bad_phase"
        ws.send_json({"type": "phase.advance", "to": "coding"})
        receive_until(ws, state_in("coding"))
        ws.send_json({"type": "phase.advance", "to": "clarify"})
        assert receive_until(ws, lambda m: m["type"] == "error")["code"] == "bad_phase"
        ws.send_json({"type": "phase.advance", "to": "wrap_up"})
        receive_until(ws, state_in("wrap_up"))


def test_chat_is_recorded_and_broadcast_to_every_tab(client: TestClient) -> None:
    session = new_session(client)
    url = f"/ws/sessions/{session['id']}"
    with client.websocket_connect(url) as first, client.websocket_connect(url) as second:
        receive_until(first, state_in("clarify"))
        sync(second)
        first.send_json({"type": "chat.send", "text": "Can the list be empty?"})
        for ws in (first, second):
            update = receive_until(ws, lambda m: m["type"] == "transcript.update")
            assert update["turn"]["text"] == "Can the list be empty?"
            assert update["turn"]["speaker"] == "candidate" and update["turn"]["source"] == "text"
    events = client.get(f"/api/sessions/{session['id']}/timeline").json()
    said = [e for e in events if e["kind"] == "transcript" and e["payload"]["speaker"] == "candidate"]
    assert len(said) == 1


def test_unsupported_messages_get_an_error(client: TestClient) -> None:
    session = new_session(client)
    with client.websocket_connect(f"/ws/sessions/{session['id']}") as ws:
        receive_until(ws, state_in("clarify"))
        ws.send_json({"type": "defense.run_chaos", "finding_id": "f1"})
        assert receive_until(ws, lambda m: m["type"] == "error")["code"] == "unsupported"


def test_session_end_over_the_socket(client: TestClient) -> None:
    session = new_session(client)
    with client.websocket_connect(f"/ws/sessions/{session['id']}") as ws:
        receive_until(ws, state_in("clarify"))
        ws.send_json({"type": "session.end"})
        state = receive_until(ws, state_in("ended"))
    assert state["remaining_s"] is None
    assert client.get(f"/api/sessions/{session['id']}").json()["ended_at"] is not None


def test_end_over_rest_for_a_session_nobody_joined(client: TestClient) -> None:
    session = new_session(client)
    response = client.post(f"/api/sessions/{session['id']}/end")
    assert response.status_code == 200
    assert response.json()["phase"] == "ended"


def test_analysis_stays_hidden_until_the_session_ends(client: TestClient) -> None:
    session = new_session(client)
    sid = session["id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        receive_until(ws, state_in("clarify"))
        runtime = hub(client).runtimes[sid]
        analysis = {
            "steps": [],
            "issues": [],
            "stated_plan": None,
            "plan_matches_code": None,
            "chosen_approach": None,
            "explanation_quality": "none",
            "proposal": None,
        }
        client.portal.call(runtime.timeline.append, TimelineKind.ANALYSIS, analysis)
        live = [e["kind"] for e in client.get(f"/api/sessions/{sid}/timeline").json()]
        assert "analysis" not in live
        ws.send_json({"type": "session.end"})
        receive_until(ws, state_in("ended"))
    finished = [e["kind"] for e in client.get(f"/api/sessions/{sid}/timeline").json()]
    assert "analysis" in finished


def test_an_edit_that_does_not_fit_leaves_a_system_note(client: TestClient) -> None:
    session = new_session(client)
    sid = session["id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        receive_until(ws, state_in("clarify"))
        ws.send_json({"type": "editor.events", "events": [edit(1000, 2, 50, "x", length=3)]})
        sync(ws)
        notes = [e for e in hub(client).runtimes[sid].timeline.tail([TimelineKind.SYSTEM])]
    assert len(notes) == 1 and "didn't fit" in notes[0].payload["message"]


def test_an_idle_runtime_expires_and_reopens_where_it_left_off(client: TestClient) -> None:
    session = new_session(client)
    sid = session["id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        receive_until(ws, state_in("clarify"))
        ws.send_json({"type": "editor.events", "events": [edit(1000, 2, 0, "x = 1\n")]})
        sync(ws)
    deadline = time.monotonic() + 5
    while sid in hub(client).runtimes and time.monotonic() < deadline:
        time.sleep(0.05)
    assert sid not in hub(client).runtimes
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        state = sync(ws)
        assert state["phase"] == "clarify"  # not restarted
        assert hub(client).runtimes[sid].code.code() == "x = 1\n"
        ws.send_json({"type": "chat.send", "text": "back"})
        sync(ws)
    seqs = [e["seq"] for e in client.get(f"/api/sessions/{sid}/timeline").json()]
    assert seqs == list(range(1, len(seqs) + 1))


# --- what the candidate says is on screen before what it triggers ------------------------------------------------


class ReplyingController:
    """Answers every candidate turn at once, like the coding wrap-up's next question or closing line."""

    def allowed_transitions(self) -> dict:
        return {}

    async def on_start(self, rt: Any) -> None:
        return None

    async def on_resume(self, rt: Any) -> None:
        return None

    async def on_client_message(self, rt: Any, msg: object) -> bool:
        return False

    async def on_timeline(self, rt: Any, event: Any) -> None:
        if event.kind == TimelineKind.TRANSCRIPT and event.payload["speaker"] == "candidate":
            await rt.note("info", "the mode reacted")
            await rt.broadcast(
                SessionState(
                    type="session.state",
                    session=rt.session,
                    phase=rt.session.phase,
                    remaining_s=None,
                    interviewer_state="idle",
                )
            )

    async def report_extra(self, rt: Any) -> None:
        return None


@pytest.mark.asyncio
async def test_a_chat_turn_reaches_the_tabs_before_the_reaction_it_triggers() -> None:
    from tests.factories import runtime as make_runtime

    rt = make_runtime()
    rt.controller = ReplyingController()
    sent: list[str] = []

    class Tab:
        async def send_text(self, data: str) -> None:
            sent.append(json.loads(data)["type"])

    connection = rt.add(Tab())
    await rt.handle(connection, ChatSend(type="chat.send", text="O(n) time, O(1) space."))
    assert sent == ["transcript.update", "session.state"]
