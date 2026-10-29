"""App factory: health, the error envelope, and the engine wiring when the engine is merged."""

import pytest
from fastapi.testclient import TestClient

from crucible.config import Settings
from crucible.main import _engine, create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    # MOCK=False explicitly: `MOCK=1 uv run pytest` sets it in the environment, which Settings also reads.
    return Settings(
        _env_file=None, DATABASE_URL=f"sqlite:///{tmp_path / 'test.db'}", MODEL_API_KEY="", MOCK=False
    )


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


engine_only = pytest.mark.skipif(
    _engine(Settings(_env_file=None)) is None, reason="engine (#5, #8) not merged yet"
)


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
def test_defense_session_without_a_runner_is_a_clear_400(settings):
    # LocalRunner without ALLOW_LOCAL_RUNNER refuses to start (like Modal without credentials). The app
    # still starts; only the defense session is refused.
    no_runner = settings.model_copy(update={"RUNNER": "local", "ALLOW_LOCAL_RUNNER": False})
    with TestClient(create_app(no_runner)) as client:
        r = client.post("/api/sessions", json={"mode": "defense", "project_id": "bank-transfer"})
        assert r.status_code == 400 and r.json()["error"]["code"] == "bad_config"
        assert "can't run code" in r.json()["error"]["message"]


@engine_only
def test_session_quota_returns_429_after_the_daily_limit(tmp_path):
    s = Settings(
        _env_file=None,
        DATABASE_URL=f"sqlite:///{tmp_path / 'q.db'}",
        MAX_SESSIONS_PER_IP_PER_DAY=2,
        MOCK=False,
    )
    with TestClient(create_app(s)) as c:
        codes = [
            c.post("/api/sessions", json={"mode": "coding", "difficulty": "easy"}).status_code
            for _ in range(3)
        ]
        assert codes == [201, 201, 429]
        r = c.post("/api/sessions", json={"mode": "coding", "difficulty": "easy"})
        assert r.json()["error"]["code"] == "rate_limited"


@engine_only
def test_failed_session_creation_does_not_use_up_the_quota(tmp_path):
    s = Settings(
        _env_file=None,
        DATABASE_URL=f"sqlite:///{tmp_path / 'q.db'}",
        MAX_SESSIONS_PER_IP_PER_DAY=1,
        MOCK=False,
    )
    with TestClient(create_app(s)) as c:
        assert c.post("/api/sessions", json={"mode": "chess"}).status_code == 422
        assert c.post("/api/sessions", json={"mode": "coding", "difficulty": "easy"}).status_code == 201


def test_production_refuses_dev_only_settings():
    s = Settings(_env_file=None, APP_ENV="prod", DEFENSE_DEV_API=True, CORS_ORIGINS="http://localhost:3000")
    with pytest.raises(RuntimeError, match=r"DEFENSE_DEV_API.*CORS_ORIGINS"):
        create_app(s)


def test_railway_counts_as_production():
    s = Settings(_env_file=None, RAILWAY_ENVIRONMENT_NAME="production", CORS_ORIGINS="https://crucible.app")
    assert s.is_production and s.production_problems() == []


def test_dev_settings_are_allowed_outside_production():
    assert not Settings(_env_file=None, DEFENSE_DEV_API=True).is_production
