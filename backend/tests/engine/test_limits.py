"""Pre-deploy limits (PLAN §8.2, §8.3): message sizes, and the per-connection rate on both sockets."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
from starlette.websockets import WebSocketDisconnect

from crucible.contracts.ws import MAX_CHAT_CHARS, ClientMessage
from crucible.engine.api import FLOOD_CLOSE, MAX_MESSAGE_CHARS
from crucible.engine.limits import AUDIO_BURST, SESSION_BURST, MessageGate, TokenBucket
from tests.engine.test_voice import FRAME, FakeASR, FakeStream, make_client, new_session, receive_until

CLIENT_MESSAGE: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


# --- the limiter ----------------------------------------------------------------------------------------------


def test_a_bucket_allows_the_burst_then_refills_at_the_rate() -> None:
    clock = Clock()
    bucket = TokenBucket(rate_per_s=8, burst=3, clock=clock)
    assert [bucket.take() for _ in range(4)] == [True, True, True, False]
    clock.now += 0.125  # one token back (an exact binary fraction, so no float rounding)
    assert [bucket.take() for _ in range(2)] == [True, False]
    clock.now += 60  # never more than the burst
    assert sum(bucket.take() for _ in range(10)) == 3


def test_a_gate_drops_over_the_rate_and_closes_a_flood() -> None:
    clock = Clock()
    gate = MessageGate(TokenBucket(rate_per_s=1, burst=1, clock=clock), clock, window_s=10, max_drops=3)
    assert [gate.check() for _ in range(4)] == ["ok", "drop", "drop", "close"]


def test_drops_spread_out_over_time_dont_close() -> None:
    clock = Clock()
    gate = MessageGate(TokenBucket(rate_per_s=0, burst=0, clock=clock), clock, window_s=10, max_drops=3)
    verdicts = []
    for _ in range(6):
        verdicts.append(gate.check())
        clock.now += 6  # each drop leaves the window before the third arrives
    assert set(verdicts) == {"drop"}


# --- sizes ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        {"type": "chat.send", "text": "x" * (MAX_CHAT_CHARS + 1)},
        {"type": "code.run", "file": "solution.py", "code": "x" * 200_001},
        {"type": "editor.events", "events": [{"t": 0, "version": 1, "kind": "focus"}] * 501},
        {"type": "defense.verify", "finding_id": "f1", "files": {f"f{i}.py": "" for i in range(61)}},
        {"type": "hint.request", "step_id": "s" * 65},
    ],
)
def test_oversized_client_fields_are_rejected(message: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CLIENT_MESSAGE.validate_python(message)


def test_real_messages_fit() -> None:
    CLIENT_MESSAGE.validate_python({"type": "chat.send", "text": "Can the list be empty?" * 100})
    CLIENT_MESSAGE.validate_python({"type": "code.submit", "file": "solution.py", "code": "x = 1\n" * 2_000})


# --- the session socket --------------------------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with make_client(tmp_path, FakeASR(FakeStream())) as test_client:
        yield test_client


def joined(client: TestClient) -> tuple[str, Any]:
    sid = new_session(client)
    return sid, client.websocket_connect(f"/ws/sessions/{sid}")


def test_a_message_over_the_size_cap_is_refused_before_parsing(client: TestClient) -> None:
    _, socket = joined(client)
    with socket as ws:
        receive_until(ws, lambda m: m["type"] == "session.state" and m["phase"] == "clarify")
        ws.send_text(json.dumps({"type": "chat.send", "text": "x" * (MAX_MESSAGE_CHARS + 1)}))
        error = receive_until(ws, lambda m: m["type"] == "error")
        assert error["code"] == "too_large"
        ws.send_json({"type": "chat.send", "text": "x" * (MAX_CHAT_CHARS + 1)})
        error = receive_until(ws, lambda m: m["type"] == "error")
        assert error["code"] == "bad_message" and "text" in error["message"]


def test_a_burst_over_the_rate_gets_one_warning_and_the_socket_keeps_working(client: TestClient) -> None:
    _, socket = joined(client)
    with socket as ws:
        receive_until(ws, lambda m: m["type"] == "session.state" and m["phase"] == "clarify")
        for _ in range(SESSION_BURST + 20):
            ws.send_json({"type": "hello", "client_now_ms": 0})
        seen: list[str] = []
        while not seen or seen[-1] != "error":
            seen.append(ws.receive_json()["type"])
        assert seen.count("error") == 1  # one warning, not one per dropped message
        assert SESSION_BURST <= seen.count("session.state") <= SESSION_BURST + 5


def test_a_flood_closes_the_socket(client: TestClient) -> None:
    _, socket = joined(client)
    with socket as ws, pytest.raises(WebSocketDisconnect) as closed:
        receive_until(ws, lambda m: m["type"] == "session.state" and m["phase"] == "clarify")
        for _ in range(SESSION_BURST + 250):
            ws.send_json({"type": "hello", "client_now_ms": 0})
        for _ in range(SESSION_BURST + 260):
            ws.receive_json()
    assert closed.value.code == FLOOD_CLOSE


# --- the audio socket ------------------------------------------------------------------------------------------------


def test_oversized_audio_frames_are_dropped(tmp_path: Path) -> None:
    stream = FakeStream()
    with make_client(tmp_path, FakeASR(stream)) as client:
        sid, socket = joined(client)
        with socket as ws, client.websocket_connect(f"/ws/sessions/{sid}/audio") as audio:
            receive_until(ws, lambda m: m["type"] == "session.state" and m["phase"] == "clarify")
            audio.send_text(json.dumps({"type": "start"}))
            bridge = client.app.state.hub.runtimes[sid].voice
            client.portal.call(_until_streaming, bridge)
            audio.send_bytes(b"\x00" * 10_000)  # not a real frame
            audio.send_bytes(FRAME)
            client.portal.call(_until_frames, stream, 1)
    assert stream.frames == [FRAME]


def test_audio_faster_than_real_time_is_dropped_then_closed(tmp_path: Path) -> None:
    stream = FakeStream()
    with make_client(tmp_path, FakeASR(stream)) as client:
        sid, socket = joined(client)
        with socket as ws, client.websocket_connect(f"/ws/sessions/{sid}/audio") as audio:
            receive_until(ws, lambda m: m["type"] == "session.state" and m["phase"] == "clarify")
            audio.send_text(json.dumps({"type": "start"}))
            client.portal.call(_until_streaming, client.app.state.hub.runtimes[sid].voice)
            for _ in range(AUDIO_BURST + 250):
                audio.send_bytes(FRAME)
            with pytest.raises(WebSocketDisconnect) as closed:
                audio.receive_bytes()
    assert closed.value.code == FLOOD_CLOSE
    assert len(stream.frames) <= AUDIO_BURST + 5  # never forwarded faster than the burst allows


async def _until_streaming(bridge: Any) -> None:
    from tests.engine.test_voice import until

    await until(lambda: bridge.streaming)


async def _until_frames(stream: FakeStream, n: int) -> None:
    from tests.engine.test_voice import until

    await until(lambda: len(stream.frames) >= n)
