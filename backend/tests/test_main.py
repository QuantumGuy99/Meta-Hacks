"""App factory: health, the error envelope, and the engine wiring when the engine is merged."""

import pytest
from fastapi.testclient import TestClient

from crucible.config import Settings
from crucible.main import _engine, create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(_env_file=None, DATABASE_URL=f"sqlite:///{tmp_path / 'test.db'}", MODEL_API_KEY="")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def test_health_matches_the_health_contract(client):
    assert client.get("/api/health").json() == {"ok": True, "version": "0.1.0", "mock": False}


def test_unknown_route_uses_the_error_envelope(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "not_found", "message": "Not Found"}}


def test_database_url_must_be_sqlite():
    with pytest.raises(ValueError):
        _ = Settings(_env_file=None, DATABASE_URL="postgres://x").database_path
    assert Settings(_env_file=None, DATABASE_URL="sqlite:///:memory:").database_path is None


engine_only = pytest.mark.skipif(_engine() is None, reason="engine (#5, #8) not merged yet")


@engine_only
def test_validation_errors_use_the_error_envelope(client):
    r = client.post("/api/sessions", json={"mode": "chess"})
    assert r.status_code == 422
    assert set(r.json()) == {"error"} and r.json()["error"]["code"] == "invalid_request"


@engine_only
def test_coding_session_round_trip_persists_to_sqlite(settings):
    with TestClient(create_app(settings)) as c:
        r = c.post("/api/sessions", json={"mode": "coding", "difficulty": "easy"})
        assert r.status_code == 201, r.text
        session_id = r.json()["id"]
        with c.websocket_connect(f"/ws/sessions/{session_id}") as ws:
            ws.send_json({"type": "hello", "client_now_ms": 0})
            assert ws.receive_json()["type"] == "session.state"
    with TestClient(create_app(settings)) as c:  # a fresh app reads the same file
        assert c.get(f"/api/sessions/{session_id}").status_code == 200
        assert isinstance(c.get(f"/api/sessions/{session_id}/timeline").json(), list)


@engine_only
def test_defense_sessions_are_unavailable_until_defense_controller_lands(client):
    r = client.post("/api/sessions", json={"mode": "defense", "project_id": "bank-transfer"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "mode_unavailable"
