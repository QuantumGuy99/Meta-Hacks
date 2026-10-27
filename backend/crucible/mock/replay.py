"""Replays `fixtures/<scenario>.jsonl` over the session API and WebSocket (PLAN §14.6).

Each line is `{"dt_ms": <ms since the previous line>, "msg": <ServerMessage>}`. In MOCK mode a session's id is
its scenario name (`/defense/defense-bank-transfer`). Client messages are accepted and logged, not answered.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter

from crucible.contracts.common import Mode, Session, SessionConfig
from crucible.contracts.ws import ServerMessage

logger = logging.getLogger(__name__)

FIXTURES = Path(__file__).parent / "fixtures"
DEFAULT_SCENARIO = {Mode.CODING: "coding-active", Mode.DEFENSE: "defense-bank-transfer"}
UNKNOWN_SESSION_CLOSE = 4404
SERVER_MESSAGE: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)

router = APIRouter(tags=["mock"])


@lru_cache
def load_scenario(name: str) -> list[tuple[int, dict]]:
    """[(dt_ms, message)], every message validated against the contracts. KeyError if it doesn't exist."""
    path = FIXTURES / f"{name}.jsonl"
    if not path.is_file():
        raise KeyError(name)
    lines = []
    for raw in path.read_text().splitlines():
        if raw.strip():
            item = json.loads(raw)
            SERVER_MESSAGE.validate_python(item["msg"])
            lines.append((int(item["dt_ms"]), item["msg"]))
    return lines


def scenarios() -> list[str]:
    return sorted(p.stem for p in FIXTURES.glob("*.jsonl"))


def scenario_session(name: str) -> Session:
    """The session the recording started with (its first session.state), under the scenario's name."""
    for _, msg in load_scenario(name):
        if msg["type"] == "session.state":
            return Session.model_validate({**msg["session"], "id": name})
    raise KeyError(name)


@router.post("/api/sessions", status_code=201, response_model=Session)
async def create_session(config: SessionConfig) -> Session | JSONResponse:
    name = DEFAULT_SCENARIO[config.mode]
    try:
        return scenario_session(name)
    except KeyError:
        return _error(400, "mode_unavailable", f"no MOCK recording for {config.mode} yet ({name}.jsonl)")


@router.get("/api/sessions/{session_id}", response_model=Session)
async def get_session(session_id: str) -> Session | JSONResponse:
    try:
        return scenario_session(session_id)
    except KeyError:
        return _error(404, "not_found", f"no MOCK scenario {session_id!r}; have {scenarios()}")


@router.websocket("/ws/sessions/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str) -> None:
    try:
        lines = load_scenario(session_id)
    except KeyError:
        await websocket.close(code=UNKNOWN_SESSION_CLOSE)
        return
    await websocket.accept()
    speed = max(getattr(websocket.app.state.settings, "MOCK_SPEED", 1.0), 0.01)
    listener = asyncio.create_task(_log_client(websocket, session_id))
    try:
        for dt_ms, msg in lines:
            await asyncio.sleep(dt_ms / 1000 / speed)
            await websocket.send_text(json.dumps(_renamed(msg, session_id)))
        await listener  # keep the socket open until the client leaves
    except WebSocketDisconnect:
        pass
    finally:
        listener.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await listener


async def _log_client(websocket: WebSocket, session_id: str) -> None:
    with contextlib.suppress(WebSocketDisconnect):
        while True:
            text = await websocket.receive_text()
            logger.info("MOCK %s ← %s", session_id, text[:200])


def _renamed(msg: dict, session_id: str) -> dict:
    if msg["type"] == "session.state":
        return {**msg, "session": {**msg["session"], "id": session_id}}
    return msg


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


__all__ = ["load_scenario", "router", "scenarios"]
