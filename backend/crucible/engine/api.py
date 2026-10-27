"""Session REST routes and the session WebSocket (PLAN §8.1, §8.2).

The app (main.py, S-0) includes `router` and puts a `SessionHub` on `app.state.hub` at startup.
"""

import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from crucible.contracts.common import ApiError, ApiErrorBody, Session, SessionConfig
from crucible.contracts.events import TimelineEvent
from crucible.contracts.ws import ClientMessage
from crucible.engine.hub import FINISHED, ModeUnavailable, PhaseError, SessionHub, SessionSetupError
from crucible.engine.timeline import public_view

logger = logging.getLogger(__name__)

router = APIRouter()
CLIENT_MESSAGE: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)
SESSION_NOT_FOUND_CLOSE = 4404  # WebSocket close code for an unknown session id


@router.post("/api/sessions", status_code=201, response_model=Session, responses={400: {"model": ApiError}})
async def create_session(config: SessionConfig, request: Request) -> Session | JSONResponse:
    try:
        return await _hub(request).create_session(config)
    except ModeUnavailable as exc:
        return _error(400, "mode_unavailable", str(exc))
    except SessionSetupError as exc:
        return _error(400, "bad_config", str(exc))


@router.get("/api/sessions/{session_id}", response_model=Session, responses={404: {"model": ApiError}})
async def get_session(session_id: str, request: Request) -> Session | JSONResponse:
    session = await _hub(request).get_session(session_id)
    return session if session is not None else _not_found(session_id)


@router.post("/api/sessions/{session_id}/end", response_model=Session, responses={404: {"model": ApiError}})
async def end_session(session_id: str, request: Request) -> Session | JSONResponse:
    hub = _hub(request)
    if await hub.get_session(session_id) is None:
        return _not_found(session_id)
    return await hub.end_session(session_id)


@router.get(
    "/api/sessions/{session_id}/timeline",
    response_model=list[TimelineEvent],
    responses={404: {"model": ApiError}},
)
async def get_timeline(session_id: str, request: Request) -> list[TimelineEvent] | JSONResponse:
    """The replay feed. Hidden-test details never appear; hints and answers stay hidden while it's live."""
    hub = _hub(request)
    session = await hub.get_session(session_id)
    if session is None:
        return _not_found(session_id)
    events = await hub.read_timeline(session_id)
    return public_view(events, live=session.phase not in FINISHED)


@router.websocket("/ws/sessions/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str) -> None:
    hub: SessionHub = websocket.app.state.hub
    if await hub.get_session(session_id) is None:
        await websocket.close(code=SESSION_NOT_FOUND_CLOSE)
        return
    await websocket.accept()
    runtime, connection = await hub.connect(session_id, websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = CLIENT_MESSAGE.validate_json(raw)
            except ValidationError as exc:
                await runtime.error(connection, "bad_message", _first_error(exc))
                continue
            try:
                await runtime.handle(connection, msg)
            except PhaseError as exc:
                await runtime.error(connection, "bad_phase", str(exc))
            except Exception:
                logger.exception("handling %s in %s failed", msg.type, session_id)
                await runtime.error(
                    connection, "internal", "Something went wrong on our side.", retryable=True
                )
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(session_id, connection)


def _hub(request: Request) -> SessionHub:
    return request.app.state.hub


def _error(status: int, code: str, message: str) -> JSONResponse:
    body = ApiError(error=ApiErrorBody(code=code, message=message))
    return JSONResponse(status_code=status, content=body.model_dump())


def _not_found(session_id: str) -> JSONResponse:
    return _error(404, "session_not_found", f"No session with id {session_id}.")


def _first_error(exc: ValidationError) -> str:
    first = exc.errors()[0]
    where = ".".join(str(part) for part in first["loc"]) or "message"
    return f"{where}: {first['msg']}"
