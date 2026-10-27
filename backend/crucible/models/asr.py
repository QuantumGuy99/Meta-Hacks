"""Muse Voice Transcribe: the realtime transcription socket and the file endpoint (PLAN §9.7, V1).

Realtime (checked against dev.meta.ai/docs/api-reference/voice on 2026-10-27): connect, send the handshake as the
first text frame within 10 s, read the acknowledgement (`{"sessionId": …}`, the only frame without `type`), then
send binary PCM at real-time pace and read typed JSON events. `{"type":"endStream"}` ends the input; the server
sends what's left, then closes with 1000.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import wave
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

logger = logging.getLogger(__name__)

REALTIME_URL = "wss://api.meta.ai/v1/asr/realtime"
MODEL = "muse-voice-transcribe-1.0"
HANDSHAKE_TIMEOUT_S = 10  # the server drops a socket that hasn't sent its handshake by then
TRANSCRIBE_TIMEOUT_S = 30
SAMPLE_RATE = 24_000
BYTES_PER_MS = SAMPLE_RATE * 2 // 1000  # 16-bit mono: 48 bytes per ms
LANGUAGES = ["English"]
CLOSE_ABNORMAL = 1006  # the socket dropped without a close frame


@dataclass(frozen=True, slots=True)
class ASRSettings:
    api_key: str = field(repr=False)
    realtime_url: str = REALTIME_URL
    model: str = MODEL

    @property
    def transcribe_url(self) -> str:
        """The file endpoint next to the realtime one: wss://…/v1/asr/realtime → https://…/v1/asr/transcribe."""
        base = self.realtime_url.replace("wss://", "https://", 1).replace("ws://", "http://", 1)
        return base.rsplit("/", 1)[0] + "/transcribe"


class ASRError(Exception):
    """Transcription failed. `code` is the realtime close code (1006 if the socket dropped, None for HTTP)."""

    def __init__(self, message: str, *, code: int | None = None, reason: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.reason = reason


# --- server events (lenient: the docs say new fields and types may appear) -----------------------------------


class _Event(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)


class SpeechStart(_Event):
    type: Literal["speechStart"]
    turn_id: int = Field(alias="turnId")
    audio_ms: int = Field(alias="audioProcessedMs")


class Partial(_Event):  # cumulative: each one replaces the last for the open turn; it carries no turn id
    type: Literal["transcript"]
    text: str = Field(alias="transcript")
    final: bool
    audio_ms: int = Field(alias="audioProcessedMs")


class SpeechEnd(_Event):
    type: Literal["speechEnd"]
    turn_id: int = Field(alias="turnId")
    audio_ms: int = Field(alias="audioProcessedMs")


class SpeechComplete(_Event):  # the turn's final text, which may differ from its last partial
    type: Literal["speechComplete"]
    turn_id: int = Field(alias="turnId")
    text: str = Field(alias="transcript")
    audio_ms: int = Field(alias="audioProcessedMs")


class ErrorEvent(_Event):
    type: Literal["error"]
    message: str
    error_code: str | None = Field(default=None, alias="errorCode")


ASREvent = Annotated[
    SpeechStart | Partial | SpeechEnd | SpeechComplete | ErrorEvent, Field(discriminator="type")
]
_EVENT: TypeAdapter[ASREvent] = TypeAdapter(ASREvent)
_KNOWN = frozenset({"speechStart", "transcript", "speechEnd", "speechComplete", "error"})


def parse_event(raw: str | bytes) -> ASREvent | None:
    """A server event, or None for binary frames, `audioProgress` and types this client doesn't know."""
    if isinstance(raw, bytes):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("asr: a frame that isn't JSON (%d chars)", len(raw))
        return None
    if not isinstance(data, dict) or data.get("type") not in _KNOWN:
        return None
    try:
        return _EVENT.validate_python(data)
    except ValidationError as exc:
        logger.warning("asr: a %s event didn't match the documented fields: %s", data.get("type"), exc)
        return None


# --- realtime -----------------------------------------------------------------------------------------------------


class RealtimeStream:
    """One realtime transcription session, in ENDPOINTING mode (the model finds the turns)."""

    def __init__(self, socket: ClientConnection, session_id: str) -> None:
        self._socket = socket
        self.session_id = session_id

    @classmethod
    async def open(cls, settings: ASRSettings) -> RealtimeStream:
        handshake = {
            "authorization": {"accessToken": f"Bearer {settings.api_key}"},  # the HTTP header isn't read
            "model": settings.model,
            "audioEncoding": "PCM_24KHZ",
            "mode": "ENDPOINTING",
            "partialMode": "CUMULATIVE",
            "emitAudioProgress": False,
            "languageBias": LANGUAGES,
        }
        socket: ClientConnection | None = None
        try:
            async with asyncio.timeout(HANDSHAKE_TIMEOUT_S):
                socket = await connect(settings.realtime_url, open_timeout=None, max_size=2**20)
                await socket.send(json.dumps(handshake))
                ack = json.loads(await socket.recv())
        except ConnectionClosed as exc:
            raise _closed(exc, "closed during the handshake") from exc
        except (OSError, TimeoutError, InvalidHandshake, json.JSONDecodeError) as exc:
            if socket is not None:
                await socket.close()
            raise ASRError(f"couldn't open realtime transcription: {exc!r}", code=CLOSE_ABNORMAL) from exc
        if not isinstance(ack, dict) or "type" in ack or "sessionId" not in ack:
            await socket.close()
            message = ack.get("message", "no session id") if isinstance(ack, dict) else "bad acknowledgement"
            raise ASRError(f"realtime transcription refused the handshake: {message}", code=CLOSE_ABNORMAL)
        return cls(socket, str(ack["sessionId"]))

    async def send_audio(self, frame: bytes) -> None:
        try:
            await self._socket.send(frame)
        except ConnectionClosed as exc:
            raise _closed(exc, "closed while sending audio") from exc

    async def end_stream(self) -> None:
        with contextlib.suppress(ConnectionClosed):
            await self._socket.send(json.dumps({"type": "endStream"}))

    async def events(self) -> AsyncIterator[ASREvent]:
        """Server events until the socket closes: a normal close (1000) just ends, any other raises `ASRError`."""
        try:
            async for raw in self._socket:
                event = parse_event(raw)
                if event is not None:
                    yield event
        except ConnectionClosed as exc:
            raise _closed(exc, "realtime transcription closed") from exc

    async def close(self) -> None:
        await self._socket.close()


def _closed(exc: ConnectionClosed, what: str) -> ASRError:
    code = exc.rcvd.code if exc.rcvd is not None else CLOSE_ABNORMAL
    reason = exc.rcvd.reason if exc.rcvd is not None else ""
    return ASRError(f"{what} ({code}{': ' + reason if reason else ''})", code=code, reason=reason)


# --- file transcription (the fallback) -----------------------------------------------------------------------


class TranscribedTurn(_Event):
    turn_id: int = Field(alias="turnId")
    start_ms: int = Field(alias="startMs")
    end_ms: int = Field(alias="endMs")
    text: str = Field(alias="transcript")


class Transcription(_Event):
    session_id: str = Field(alias="sessionId")
    text: str = Field(alias="transcript")
    audio_ms: int = Field(alias="audioDurationMs")
    turns: list[TranscribedTurn]


async def transcribe_wav(
    settings: ASRSettings, wav: bytes, *, client: httpx.AsyncClient | None = None
) -> Transcription:
    """`POST /v1/asr/transcribe` with one WAV clip, in ENDPOINTING mode so the reply has turns with times."""
    request: dict[str, Any] = {
        "model": settings.model,
        "audioEncoding": "WAV",
        "mode": "ENDPOINTING",
        "languageBias": LANGUAGES,
    }
    files = {
        "request": (None, json.dumps(request), "application/json"),
        "audio": ("chunk.wav", wav, "audio/wav"),
    }
    headers = {"Authorization": f"Bearer {settings.api_key}", "Accept": "application/json"}
    try:
        async with asyncio.timeout(TRANSCRIBE_TIMEOUT_S):
            if client is None:
                async with httpx.AsyncClient() as own:
                    response = await own.post(settings.transcribe_url, files=files, headers=headers)
            else:
                response = await client.post(settings.transcribe_url, files=files, headers=headers)
        response.raise_for_status()
        return Transcription.model_validate(response.json())
    except (httpx.HTTPError, TimeoutError, ValidationError, json.JSONDecodeError) as exc:
        raise ASRError(f"file transcription failed: {exc!r}") from exc


def to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Wrap 16-bit mono PCM in a RIFF/WAVE header (in memory)."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(pcm)
    return buffer.getvalue()


class MuseASR:
    """Both endpoints behind one key: what the session hub gives each `VoiceBridge` (engine/voice.py)."""

    def __init__(self, settings: ASRSettings, *, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client

    async def open_stream(self) -> RealtimeStream:
        return await RealtimeStream.open(self._settings)

    async def transcribe(self, pcm: bytes) -> Transcription:
        return await transcribe_wav(self._settings, to_wav(pcm), client=self._client)
