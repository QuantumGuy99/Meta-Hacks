"""Session REST routes and the session WebSocket (PLAN §8.1, §8.2).

The app (main.py, S-0) includes `router` and puts a `SessionHub` on `app.state.hub` at startup.
"""

import contextlib
import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from crucible.contracts.common import ApiError, ApiErrorBody, Phase, ReportPending, Session, SessionConfig
from crucible.contracts.events import TimelineEvent
from crucible.contracts.report import Report
from crucible.contracts.ws import ClientMessage
from crucible.engine.hub import FINISHED, ModeUnavailable, PhaseError, SessionHub, SessionSetupError
from crucible.engine.timeline import public_view
from crucible.engine.voice import AudioControl, VoiceBridge

logger = logging.getLogger(__name__)

router = APIRouter()
CLIENT_MESSAGE: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)
AUDIO_CONTROL: TypeAdapter[AudioControl] = TypeAdapter(AudioControl)
SESSION_NOT_FOUND_CLOSE = 4404  # WebSocket close code for an unknown session id
# Audio socket close codes (§8.3). The browser shows "use chat" for all three.
VOICE_OFF_CLOSE = 4403  # the session was created with voice off
VOICE_UNAVAILABLE_CLOSE = 4503  # no transcription configured, or it failed for good (§9.7)
MIC_TAKEN_CLOSE = 4409  # another tab opened the audio socket


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


@router.get(
    "/api/sessions/{session_id}/report",
    response_model=Report,
    responses={202: {"model": ReportPending}, 404: {"model": ApiError}, 409: {"model": ApiError}},
)
async def get_report(session_id: str, request: Request) -> Report | JSONResponse:
    """The report once it's built; 202 while it's generating (§8.1)."""
    hub = _hub(request)
    session = await hub.get_session(session_id)
    if session is None:
        return _not_found(session_id)
    report = await hub.report(session_id)
    if report is not None:
        return report
    if session.phase in (Phase.ENDED, Phase.REPORTING):
        return JSONResponse(status_code=202, content=ReportPending(status="generating").model_dump())
    if session.phase in FINISHED:
        return _error(404, "report_unavailable", "This session failed before it could be reported on.")
    return _error(409, "session_live", "The report is built once the session ends.")


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


@router.websocket("/ws/sessions/{session_id}/audio")
async def audio_socket(websocket: WebSocket, session_id: str) -> None:
    """Raw PCM from the candidate's microphone plus start/stop/ask text frames (§8.3), into the VoiceBridge."""
    hub: SessionHub = websocket.app.state.hub
    session = await hub.get_session(session_id)
    if session is None:
        await websocket.close(code=SESSION_NOT_FOUND_CLOSE)
        return
    if not session.config.voice:
        await websocket.close(code=VOICE_OFF_CLOSE, reason="voice is off for this session")
        return
    await websocket.accept()
    runtime = await hub.runtime(session_id)
    bridge = hub.voice(runtime)
    if bridge is None or bridge.state == "unavailable":
        await websocket.close(code=VOICE_UNAVAILABLE_CLOSE, reason="voice isn't available")
        return
    previous, runtime.audio_socket = runtime.audio_socket, websocket
    if isinstance(previous, WebSocket):
        with contextlib.suppress(RuntimeError):  # it may have closed already
            await previous.close(code=MIC_TAKEN_CLOSE, reason="another tab took the microphone")
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                await bridge.audio(message["bytes"])
            elif message.get("text") is not None:
                await _audio_control(bridge, message["text"])
            if not runtime.live:
                await websocket.close(code=1000, reason="the session ended")
                break
            if bridge.state == "unavailable":
                await websocket.close(code=VOICE_UNAVAILABLE_CLOSE, reason="voice isn't available")
                break
    except WebSocketDisconnect:
        pass
    finally:
        if runtime.audio_socket is websocket:
            runtime.audio_socket = None
            await bridge.stop()


async def _audio_control(bridge: VoiceBridge, raw: str) -> None:
    try:
        control = AUDIO_CONTROL.validate_json(raw)
    except ValidationError as exc:
        logger.warning("ignoring an audio control frame: %s", _first_error(exc))
        return
    match control.type:
        case "start":
            bridge.start()
        case "stop":
            await bridge.stop()
        case "ask":
            bridge.ask(control.holding)


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
