"""Record a MOCK fixture from a real local Defense session (no API key: every model stage uses its fallback).

    uv run python -m crucible.mock.record defense-bank-transfer --apps-dir tests/fixtures/apps \\
        --project bank-transfer-min --duration 6 [--report report-defense]

Drives the real hub over the WebSocket: audit → chaos → a chat answer to the grill → verify with the
reference fix → verdict, and writes every server message with its real timing to mock/fixtures/<name>.jsonl.
With --report, it also waits for the session's report and saves the session, report and timeline as
mock/fixtures/rest/<report>.json (served by MOCK mode's report page endpoints).
Re-record whenever the contracts or the flow change (CI validates every fixture line).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from crucible.config import Settings
from crucible.contracts.common import Mode
from crucible.defense.controller import make_mode
from crucible.defense.projects import load_samples
from crucible.engine.api import router
from crucible.engine.hub import SessionHub
from crucible.engine.store import MemoryStore
from crucible.mock.replay import FIXTURES, REST_FIXTURES
from crucible.runner.local import LocalRunner

ANSWER = (
    "The transfer reads both balances, awaits the fraud check, then writes values computed from that stale "
    "read, so concurrent transfers overwrite each other: a read-modify-write race with lost updates. While one "
    "request waits at the await, others read and write the same accounts. I'd make the read, the funds check "
    "and the write atomic with a lock or a transaction."
)
MAX_MESSAGES = 2000
REPORT_WAIT_S = 90


def record(name: str, apps_dir: Path, project: str, duration_s: int, report: str | None = None) -> Path:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="sqlite:///:memory:",
        RUNNER="local",
        ALLOW_LOCAL_RUNNER=True,
        LOCAL_RUNNER_ISOLATE=False,
        MODEL_API_KEY="",
    )
    samples = load_samples(apps_dir)
    if project not in samples:
        sys.exit(f"unknown project {project!r}; have {sorted(samples)}")
    mode = make_mode(settings, samples=samples, runner=LocalRunner(settings), duration_override_s=duration_s)
    app = FastAPI()
    app.include_router(router)
    app.state.hub = SessionHub(MemoryStore(), {Mode.DEFENSE: mode})
    lines: list[dict] = []
    with TestClient(app) as client:
        session_id = client.post("/api/sessions", json={"mode": "defense", "project_id": project}).json()[
            "id"
        ]
        with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
            last = time.monotonic()

            def until(done) -> dict:
                nonlocal last
                for _ in range(MAX_MESSAGES):
                    msg = ws.receive_json()
                    now = time.monotonic()
                    lines.append({"dt_ms": round((now - last) * 1000), "msg": msg})
                    last = now
                    if done(msg):
                        return msg
                sys.exit("the session never reached the expected step")

            ws.send_json({"type": "hello", "client_now_ms": 0})
            until(lambda m: m["type"] == "interviewer.message")  # first grill question
            ws.send_json({"type": "chat.send", "text": ANSWER})
            until(lambda m: m["type"] == "session.state" and m["phase"] == "fix")
            fixed = samples[project].fixed_files or {}
            ws.send_json({"type": "defense.verify", "finding_id": "f1", "files": fixed})
            until(lambda m: m["type"] == "session.state" and m["phase"] == "ended")
        if report:
            _save_report(client, session_id, report)
    out = FIXTURES / f"{name}.jsonl"
    out.write_text("".join(json.dumps(line) + "\n" for line in lines))
    return out


def _save_report(client: TestClient, session_id: str, name: str) -> Path:
    """The finished session's report page data, renamed to `name` like the replayed sessions are."""
    deadline = time.monotonic() + REPORT_WAIT_S
    while (r := client.get(f"/api/sessions/{session_id}/report")).status_code == 202:
        if time.monotonic() > deadline:
            sys.exit(f"the report wasn't ready after {REPORT_WAIT_S} s")
        time.sleep(0.5)
    if r.status_code != 200:
        sys.exit(f"report failed: {r.status_code} {r.text[:200]}")
    data = {
        "session": client.get(f"/api/sessions/{session_id}").json() | {"id": name},
        "report": r.json() | {"session_id": name},
        "timeline": client.get(f"/api/sessions/{session_id}/timeline").json(),
    }
    REST_FIXTURES.mkdir(exist_ok=True)
    out = REST_FIXTURES / f"{name}.json"
    out.write_text(json.dumps(data, indent=1) + "\n")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m crucible.mock.record")
    ap.add_argument("name", help="scenario name, e.g. defense-bank-transfer")
    ap.add_argument("--apps-dir", type=Path, required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--duration", type=int, default=6, help="attack seconds (shorter = smaller fixture)")
    ap.add_argument("--report", default=None, help="also save the report page data, e.g. report-defense")
    args = ap.parse_args()
    path = record(args.name, args.apps_dir, args.project, args.duration, args.report)
    print(f"wrote {path} ({sum(1 for _ in path.open())} messages)")


if __name__ == "__main__":
    main()
