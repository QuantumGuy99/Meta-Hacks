"""HTTP API: health, samples and the dev pipeline run (standalone, local runner, models down)."""

import time

import pytest
from fastapi.testclient import TestClient

from crucible.defense import audit as audit_mod
from crucible.main import create_app
from tests.defense.fixtures import GOOD_ANSWER


@pytest.fixture
def client(local_settings):
    audit_mod._CACHE.clear()
    with TestClient(create_app(local_settings)) as c:
        yield c


def test_health_is_up(client):
    assert client.get("/api/health").json()["ok"] is True


def test_samples_list_the_fixture_app(client):
    ids = [p["id"] for p in client.get("/api/defense/samples").json()]
    assert "bank-transfer-min" in ids


def test_project_files_returns_the_app_source_only(client):
    body = client.get("/api/defense/projects/bank-transfer-min/files").json()
    assert body["project_id"] == "bank-transfer-min"
    assert "app/main.py" in body["files"] and "def transfer" in body["files"]["app/main.py"]
    hidden = ("flaws.json", "reference_attack.json", "fix.patch", "fixed/")
    assert not [p for p in body["files"] if any(h in p for h in hidden)]


def test_project_files_unknown_project_is_404(client):
    r = client.get("/api/defense/projects/nope/files")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_dev_run_unknown_project_is_404(client):
    assert client.post("/api/defense/dev/runs", json={"project_id": "nope", "answer": "x"}).status_code == 404


@pytest.mark.e2e
def test_dev_run_end_to_end(client):
    r = client.post(
        "/api/defense/dev/runs",
        json={"project_id": "bank-transfer-min", "answer": GOOD_ANSWER, "duration_s": 2},
    )
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        body = client.get(f"/api/defense/dev/runs/{run_id}").json()
        if body["status"] != "running":
            break
        time.sleep(0.5)
    assert body["status"] == "done", body["error"]
    assert body["verdict"]["passed"], body["verdict"]
    assert "explanation" not in str([e for e in body["events"] if e["kind"] == "audit"])


def test_dev_api_is_off_by_default(local_settings):
    off = local_settings.model_copy(update={"DEFENSE_DEV_API": False})
    with TestClient(create_app(off)) as c:
        assert c.post("/api/defense/dev/runs", json={}).status_code == 404
