"""MOCK replay (OPS-2, PLAN §14.6): fixtures match the contracts; REST and WebSocket replay them."""

import pytest
from fastapi.testclient import TestClient

from crucible.config import Settings
from crucible.main import create_app
from crucible.mock.replay import load_scenario, scenarios

SCENARIO = "defense-bank-transfer"


def test_every_fixture_line_is_a_valid_server_message():
    assert scenarios(), "no fixtures recorded"
    for name in scenarios():
        load_scenario.cache_clear()
        assert load_scenario(name)  # validates every line against ServerMessage


def test_defense_fixture_tells_the_whole_story():
    types = [m["type"] for _, m in load_scenario(SCENARIO)]
    for t in (
        "session.state",
        "defense.audit",
        "defense.chaos.metric",
        "defense.chaos.done",
        "interviewer.message",
        "defense.grill.eval",
        "defense.verdict",
    ):
        assert t in types, t
    audit = next(m for _, m in load_scenario(SCENARIO) if m["type"] == "defense.audit")
    assert "explanation" not in str(audit)  # the recording keeps the answer hidden too


@pytest.fixture
def client(tmp_path):
    settings = Settings(_env_file=None, DATABASE_URL="sqlite:///:memory:", MOCK=True, MOCK_SPEED=100.0)
    with TestClient(create_app(settings)) as c:
        yield c


def test_mock_session_id_is_the_scenario_name(client):
    r = client.post("/api/sessions", json={"mode": "defense", "project_id": "anything"})
    assert r.status_code == 201 and r.json()["id"] == SCENARIO
    assert client.get(f"/api/sessions/{SCENARIO}").json()["id"] == SCENARIO
    assert client.get("/api/sessions/nope").status_code == 404
    assert client.get("/api/health").json()["mock"] is True


def test_websocket_replays_the_recording_and_ignores_client_messages(client):
    expected = [m["type"] for _, m in load_scenario(SCENARIO)]
    with client.websocket_connect(f"/ws/sessions/{SCENARIO}") as ws:
        ws.send_json({"type": "hello", "client_now_ms": 0})  # accepted, logged, not answered
        got = [ws.receive_json() for _ in expected]
    assert [m["type"] for m in got] == expected
    assert got[0]["session"]["id"] == SCENARIO


def test_unknown_scenario_closes_the_socket(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/sessions/nope") as ws:
        ws.receive_json()
