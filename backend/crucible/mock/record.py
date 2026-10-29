"""Record a MOCK fixture from a real local Defense session (no API key: every model stage uses its fallback).

    uv run python -m crucible.mock.record defense-bank-transfer --apps-dir tests/fixtures/apps \\
        --project bank-transfer-min --duration 6

Drives the real hub over the WebSocket: audit → chaos → a chat answer to the grill → verify with the
reference fix → verdict, and writes every server message with its real timing to mock/fixtures/<name>.jsonl.
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
from crucible.mock.replay import FIXTURES
from crucible.runner.local import LocalRunner

ANSWER = (
    "The transfer reads both balances, awaits the fraud check, then writes values computed from that stale "
    "read, so concurrent transfers overwrite each other: a read-modify-write race with lost updates. While one "
    "request waits at the await, others read and write the same accounts. I'd make the read, the funds check "
    "and the write atomic with a lock or a transaction."
)
MAX_MESSAGES = 2000


def record(name: str, apps_dir: Path, project: str, duration_s: int) -> Path:
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
    out = FIXTURES / f"{name}.jsonl"
    out.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m crucible.mock.record")
    ap.add_argument("name", help="scenario name, e.g. defense-bank-transfer")
    ap.add_argument("--apps-dir", type=Path, required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--duration", type=int, default=6, help="attack seconds (shorter = smaller fixture)")
    args = ap.parse_args()
    path = record(args.name, args.apps_dir, args.project, args.duration)
    print(f"wrote {path} ({sum(1 for _ in path.open())} messages)")


if __name__ == "__main__":
    main()
