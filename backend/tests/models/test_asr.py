"""Muse Voice Transcribe client (ENG-7): events, the file endpoint and the realtime socket on loopback."""

import io
import json
import wave
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from websockets.asyncio.server import ServerConnection, serve

from crucible.models.asr import (
    ASRError,
    ASRSettings,
    ErrorEvent,
    Partial,
    RealtimeStream,
    SpeechComplete,
    SpeechStart,
    parse_event,
    to_wav,
    transcribe_wav,
)

SETTINGS = ASRSettings(api_key="test-key")


# --- events ---------------------------------------------------------------------------------------------------


def test_documented_events_parse() -> None:
    assert parse_event('{"type":"speechStart","turnId":1,"audioProcessedMs":1200}') == SpeechStart(
        type="speechStart", turn_id=1, audio_ms=1200
    )
    partial = parse_event('{"type":"transcript","transcript":"how is","final":false,"audioProcessedMs":2400}')
    assert isinstance(partial, Partial) and partial.text == "how is"
    done = parse_event(
        '{"type":"speechComplete","turnId":1,"transcript":"How is it?","audioProcessedMs":3600,"extra":1}'
    )
    assert isinstance(done, SpeechComplete) and done.text == "How is it?"  # new fields are ignored
    error = parse_event('{"type":"error","message":"bad","sessionId":"","errorCode":"x"}')
    assert isinstance(error, ErrorEvent) and error.error_code == "x"


@pytest.mark.parametrize(
    "raw",
    [
        b"\x00\x01",  # binary
        '{"type":"audioProgress","audioProcessedMs":80}',  # off in our handshake; ignored anyway
        '{"type":"speaker","label":"A","audioProcessedMs":1}',  # unknown here
        "not json",
        '{"type":"speechStart","turnId":1}',  # missing a documented field
    ],
)
def test_other_frames_are_skipped(raw: str | bytes) -> None:
    assert parse_event(raw) is None


def test_the_file_endpoint_sits_next_to_realtime() -> None:
    assert SETTINGS.transcribe_url == "https://api.meta.ai/v1/asr/transcribe"
    assert ASRSettings(api_key="k", realtime_url="ws://localhost:9/v1/asr/realtime").transcribe_url == (
        "http://localhost:9/v1/asr/transcribe"
    )


# --- file transcription ---------------------------------------------------------------------------------------


def test_wav_wraps_24khz_mono_pcm() -> None:
    with wave.open(io.BytesIO(to_wav(b"\x01\x00" * 480))) as clip:
        assert (clip.getnchannels(), clip.getsampwidth(), clip.getframerate(), clip.getnframes()) == (
            1,
            2,
            24_000,
            480,
        )


@pytest.mark.asyncio
async def test_transcribe_sends_multipart_and_parses_turns() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.content
        reply = {
            "sessionId": "s",
            "transcript": "one two",
            "audioDurationMs": 10_000,
            "turns": [{"turnId": 1, "startMs": 200, "endMs": 1_500, "transcript": "one two"}],
        }
        return httpx.Response(200, json=reply)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await transcribe_wav(SETTINGS, to_wav(b"\x00\x00" * 24), client=client)
    assert seen["auth"] == "Bearer test-key"
    assert b'name="request"' in seen["body"] and b'name="audio"' in seen["body"]
    assert b'"audioEncoding": "WAV"' in seen["body"] and b'"mode": "ENDPOINTING"' in seen["body"]
    assert [(t.start_ms, t.end_ms, t.text) for t in result.turns] == [(200, 1_500, "one two")]


@pytest.mark.asyncio
async def test_a_failed_transcription_raises() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503, json={"error": "busy"}))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ASRError, match="file transcription failed"):
            await transcribe_wav(SETTINGS, to_wav(b""), client=client)


# --- realtime, against a local server -------------------------------------------------------------------------

Script = Callable[[ServerConnection, dict[str, Any]], Any]


@asynccontextmanager
async def server(script: Script) -> AsyncIterator[tuple[ASRSettings, list[Any]]]:
    """A stand-in realtime server: reads the handshake, then runs `script`. Yields settings and what it got."""
    received: list[Any] = []

    async def handle(ws: ServerConnection) -> None:
        handshake = json.loads(await ws.recv())
        received.append(handshake)
        await script(ws, handshake)

    async with serve(handle, "127.0.0.1", 0) as srv:
        port = srv.sockets[0].getsockname()[1]
        yield ASRSettings(api_key="test-key", realtime_url=f"ws://127.0.0.1:{port}/v1/asr/realtime"), received


@pytest.mark.asyncio
async def test_realtime_handshake_audio_events_and_end_stream() -> None:
    async def script(ws: ServerConnection, handshake: dict[str, Any]) -> None:
        await ws.send(json.dumps({"sessionId": "asr-1"}))
        frame = await ws.recv()
        await ws.send(json.dumps({"type": "speechStart", "turnId": 1, "audioProcessedMs": len(frame) // 48}))
        assert json.loads(await ws.recv()) == {"type": "endStream"}
        await ws.send(
            json.dumps({"type": "speechComplete", "turnId": 1, "transcript": "hi", "audioProcessedMs": 80})
        )
        await ws.close(1000)

    async with server(script) as (settings, received):
        stream = await RealtimeStream.open(settings)
        await stream.send_audio(b"\x00" * 3_840)
        events = []
        async for event in stream.events():
            events.append(event)
            if isinstance(event, SpeechStart):
                await stream.end_stream()
    assert stream.session_id == "asr-1"
    handshake = received[0]
    assert handshake["authorization"] == {"accessToken": "Bearer test-key"}
    assert (handshake["audioEncoding"], handshake["mode"], handshake["model"]) == (
        "PCM_24KHZ",
        "ENDPOINTING",
        "muse-voice-transcribe-1.0",
    )
    assert [type(e).__name__ for e in events] == ["SpeechStart", "SpeechComplete"]
    assert events[0].audio_ms == 80


@pytest.mark.asyncio
async def test_an_error_close_carries_its_code_and_reason() -> None:
    async def script(ws: ServerConnection, handshake: dict[str, Any]) -> None:
        await ws.send(json.dumps({"sessionId": "asr-2"}))
        await ws.close(1011, "Max session duration reached")

    async with server(script) as (settings, _):
        stream = await RealtimeStream.open(settings)
        with pytest.raises(ASRError) as failure:
            async for _event in stream.events():
                pass
    assert (failure.value.code, failure.value.reason) == (1011, "Max session duration reached")


@pytest.mark.asyncio
async def test_a_refused_handshake_raises() -> None:
    async def script(ws: ServerConnection, handshake: dict[str, Any]) -> None:
        await ws.send(json.dumps({"type": "error", "message": "invalid model", "sessionId": ""}))
        await ws.close(1008, "invalid request")

    async with server(script) as (settings, _):
        with pytest.raises(ASRError, match="invalid model"):
            await RealtimeStream.open(settings)


@pytest.mark.asyncio
async def test_nothing_listening_raises() -> None:
    with pytest.raises(ASRError, match="couldn't open"):
        await RealtimeStream.open(ASRSettings(api_key="k", realtime_url="ws://127.0.0.1:9/v1/asr/realtime"))
