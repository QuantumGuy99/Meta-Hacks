"""ENG-7: the VoiceBridge and the audio socket (PLAN §8.3, §9.7), against a scripted transcription service."""

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from crucible.coding.problems import ProblemBank
from crucible.coding.session import CodingMode
from crucible.contracts.common import Mode
from crucible.contracts.events import TimelineKind
from crucible.engine.api import router
from crucible.engine.hub import SessionHub
from crucible.engine.store import MemoryStore
from crucible.engine.voice import CHUNK_BYTES, VoiceBridge
from crucible.models.asr import ASRError, ASREvent, Transcription, parse_event
from tests.engine.test_answers import RoleModel
from tests.factories import runtime, write_quiet_streak

FRAME = b"\x00\x00" * 1_920  # 80 ms of silence


def start(turn: int, ms: int) -> dict[str, Any]:
    return {"type": "speechStart", "turnId": turn, "audioProcessedMs": ms}


def partial(text: str, ms: int) -> dict[str, Any]:
    return {"type": "transcript", "transcript": text, "final": False, "audioProcessedMs": ms}


def end(turn: int, ms: int) -> dict[str, Any]:
    return {"type": "speechEnd", "turnId": turn, "audioProcessedMs": ms}


def complete(turn: int, text: str, ms: int) -> dict[str, Any]:
    return {"type": "speechComplete", "turnId": turn, "transcript": text, "audioProcessedMs": ms}


class FakeStream:
    """A realtime stream: `script` maps a count of frames received to the events sent after it."""

    def __init__(
        self,
        script: dict[int, list[dict[str, Any]]] | None = None,
        *,
        on_end: list[dict[str, Any]] | None = None,
        fail: ASRError | None = None,
    ) -> None:
        self.session_id = "fake"
        self.frames: list[bytes] = []
        self.ended = False
        self._script = script or {}
        self._on_end = on_end or []
        self._queue: asyncio.Queue[dict[str, Any] | ASRError | None] = asyncio.Queue()
        if fail is not None:
            self._queue.put_nowait(fail)

    async def send_audio(self, frame: bytes) -> None:
        self.frames.append(frame)
        for raw in self._script.get(len(self.frames), []):
            self._queue.put_nowait(raw)

    async def end_stream(self) -> None:
        self.ended = True
        for raw in self._on_end:
            self._queue.put_nowait(raw)
        self._queue.put_nowait(None)  # then the server closes with 1000

    async def events(self) -> AsyncIterator[ASREvent]:
        while (item := await self._queue.get()) is not None:
            if isinstance(item, ASRError):
                raise item
            event = parse_event(json.dumps(item))
            if event is not None:
                yield event

    async def close(self) -> None:
        self._queue.put_nowait(None)


class FakeASR:
    """Hands out `streams` in order (the last one repeats); answers chunks from `transcriptions`."""

    def __init__(
        self, *streams: FakeStream | ASRError, transcriptions: tuple[dict[str, Any] | ASRError, ...] = ()
    ) -> None:
        self.streams = list(streams)
        self.transcriptions = list(transcriptions)
        self.opened = 0
        self.chunks: list[bytes] = []

    async def open_stream(self) -> FakeStream:
        self.opened += 1
        item = self.streams.pop(0) if len(self.streams) > 1 else self.streams[0]
        if isinstance(item, ASRError):
            raise item
        return item

    async def transcribe(self, pcm: bytes) -> Transcription:
        self.chunks.append(pcm)
        item = self.transcriptions.pop(0) if len(self.transcriptions) > 1 else self.transcriptions[0]
        if isinstance(item, ASRError):
            raise item
        return Transcription.model_validate(item)


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


class Tab:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_text(self, data: str) -> None:
        self.messages.append(json.loads(data))

    def of(self, kind: str) -> list[dict[str, Any]]:
        return [m for m in self.messages if m["type"] == kind]


async def until(check: Callable[[], bool], timeout_s: float = 2) -> None:
    async with asyncio.timeout(timeout_s):
        while not check():  # noqa: ASYNC110  # polls state the fakes don't signal; tests only
            await asyncio.sleep(0.005)


class Setup:
    def __init__(self, asr: FakeASR) -> None:
        self.clock = Clock()
        self.rt = runtime(monotonic=self.clock)
        self.tab = Tab()
        self.rt.add(self.tab)
        self.sleeps: list[float] = []
        self.asked: list[str] = []
        self.heard = 0
        self.rt.asked = self.asked.append  # type: ignore[method-assign]
        self.rt.heard_speech = self._heard  # type: ignore[method-assign]

        async def sleep(delay_s: float) -> None:
            self.sleeps.append(delay_s)

        self.bridge = VoiceBridge(self.rt, asr, sleep=sleep)

    def _heard(self) -> None:
        self.heard += 1

    async def frames(self, n: int) -> None:
        for _ in range(n):
            self.clock.now += 0.08
            await self.bridge.audio(FRAME)

    def turns(self) -> list[dict[str, Any]]:
        return [e.payload for e in self.rt.timeline.tail([TimelineKind.TRANSCRIPT])]

    def notes(self) -> list[str]:
        return [e.payload["message"] for e in self.rt.timeline.tail([TimelineKind.SYSTEM])]


# --- realtime ------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partials_are_shown_and_completed_turns_are_stored() -> None:
    stream = FakeStream(
        {
            1: [start(1, 0), partial("can the", 400)],
            3: [end(1, 1_200)],
            4: [complete(1, "Can the list be empty?", 1_240)],
        }
    )
    s = Setup(FakeASR(stream))
    s.clock.now += 10  # 10 s into the session
    s.bridge.start()
    await until(lambda: s.bridge.streaming)
    await s.frames(4)
    await until(lambda: bool(s.turns()))
    [turn] = s.turns()  # partials are never stored
    # The first frame arrived at 10.08 s and covered the 80 ms before it: audio time 0 is 10.0 s.
    assert (turn["text"], turn["source"], turn["final"]) == ("Can the list be empty?", "voice", True)
    assert (turn["start_ms"], turn["end_ms"]) == (10_000, 11_200)  # speechEnd's time, not speechComplete's
    [shown_partial, shown_final] = [m["turn"] for m in s.tab.of("transcript.update")]
    assert (shown_partial["text"], shown_partial["final"]) == ("can the", False)
    assert shown_partial["turn_id"] == shown_final["turn_id"] == turn["turn_id"]
    assert s.asked == []  # not holding Ask: thinking aloud, not a question
    assert s.heard == 2  # speechStart and the partial hold the interviewer
    states = [m["interviewer_state"] for m in s.tab.of("session.state")]
    assert states == ["listening", "idle"]


@pytest.mark.asyncio
async def test_a_turn_spoken_while_holding_ask_is_a_question() -> None:
    stream = FakeStream(
        {
            2: [start(1, 0)],
            4: [complete(1, "Can it be empty?", 300)],
            40: [start(2, 3_000)],
            42: [complete(2, "OK, looping now.", 3_200)],
        }
    )
    s = Setup(FakeASR(stream))
    s.bridge.start()
    await until(lambda: s.bridge.streaming)
    s.bridge.ask(True)
    await s.frames(5)
    s.bridge.ask(False)
    await s.frames(37)
    await until(lambda: len(s.turns()) == 2)
    assert s.asked == ["Can it be empty?"]


@pytest.mark.asyncio
async def test_talking_on_after_letting_go_of_ask_isnt_a_question() -> None:
    # Ask released 0.4 s into a 4.8 s turn (as in the live check): it was held for under half of it.
    stream = FakeStream({1: [start(1, 0)], 66: [complete(1, "Okay, I'll walk the list once.", 4_800)]})
    s = Setup(FakeASR(stream))
    s.bridge.start()
    await until(lambda: s.bridge.streaming)
    s.bridge.ask(True)
    await s.frames(5)  # 0.4 s
    s.bridge.ask(False)
    await s.frames(61)
    await until(lambda: bool(s.turns()))
    assert s.asked == []


@pytest.mark.asyncio
async def test_a_partial_before_speech_start_still_gets_a_turn() -> None:
    stream = FakeStream({1: [partial("hello", 200), start(7, 100), complete(7, "Hello.", 400)]})
    s = Setup(FakeASR(stream))
    s.bridge.start()
    await until(lambda: s.bridge.streaming)
    await s.frames(1)
    await until(lambda: bool(s.turns()))
    assert s.turns()[0]["text"] == "Hello."
    assert s.tab.of("transcript.update")[0]["turn"]["text"] == "hello"


@pytest.mark.asyncio
async def test_dropped_streams_reconnect_with_backoff() -> None:
    good = FakeStream({1: [start(1, 0), complete(1, "Back again.", 200)]})
    s = Setup(FakeASR(ASRError("dropped", code=1011), ASRError("slow down", code=1013), good))
    s.bridge.start()
    await until(lambda: s.bridge.streaming)
    await s.frames(1)
    await until(lambda: bool(s.turns()))
    assert s.sleeps == [0.5, 5]  # backoff, then the rate-limit wait
    assert s.bridge.state == "realtime"
    assert sum("reconnecting" in n for n in s.notes()) == 2


@pytest.mark.asyncio
async def test_the_hour_cap_reconnects_without_counting_as_a_failure() -> None:
    cap = ASRError("cap", code=1011, reason="Max session duration reached")
    good = FakeStream({1: [start(1, 0), complete(1, "Still here.", 200)]})
    s = Setup(FakeASR(*(FakeStream(fail=cap) for _ in range(4)), good))
    s.bridge.start()
    await until(lambda: s.bridge.streaming and s.bridge.state == "realtime")
    await s.frames(1)
    await until(lambda: bool(s.turns()))
    assert s.sleeps == [] and s.bridge.state == "realtime"


# --- the chunked fallback -------------------------------------------------------------------------------------


def chunk_reply(*turns: tuple[int, int, str]) -> dict[str, Any]:
    return {
        "sessionId": "c",
        "transcript": " ".join(t for _, _, t in turns),
        "audioDurationMs": 10_000,
        "turns": [
            {"turnId": i, "startMs": a, "endMs": b, "transcript": t} for i, (a, b, t) in enumerate(turns)
        ],
    }


@pytest.mark.asyncio
async def test_three_failures_switch_to_ten_second_chunks() -> None:
    reply = chunk_reply((1_000, 2_500, "Hello there."), (2_500, 2_500, "there."))  # a zero-length repeat
    asr = FakeASR(ASRError("down", code=1006), transcriptions=(reply,))
    s = Setup(asr)
    s.bridge.start()
    await until(lambda: s.bridge.state == "chunked")
    assert asr.opened == 3 and s.sleeps == [0.5, 1.0]
    await s.frames(125)  # 10 s
    await until(lambda: bool(s.turns()))
    assert len(asr.chunks) == 1 and len(asr.chunks[0]) == CHUNK_BYTES
    [turn] = s.turns()
    assert (turn["start_ms"], turn["end_ms"], turn["text"]) == (
        1_000,
        2_500,
        "Hello there.",
    )  # chunk began at 0
    assert any("10 s chunks" in n for n in s.notes())


@pytest.mark.asyncio
async def test_a_rejected_stream_goes_straight_to_chunks() -> None:
    asr = FakeASR(ASRError("policy", code=1008), transcriptions=(chunk_reply(),))
    s = Setup(asr)
    s.bridge.start()
    await until(lambda: s.bridge.state == "chunked")
    assert asr.opened == 1 and s.sleeps == []


@pytest.mark.asyncio
async def test_when_chunks_fail_too_voice_is_unavailable() -> None:
    s = Setup(FakeASR(ASRError("policy", code=1008), transcriptions=(ASRError("file endpoint down"),)))
    s.bridge.start()
    await until(lambda: s.bridge.state == "chunked")
    await s.frames(250)  # two chunks, two failures
    await until(lambda: s.bridge.state == "unavailable")
    [error] = s.tab.of("error")
    assert error["code"] == "voice_unavailable" and "chat" in error["message"]
    assert any("voice is unavailable" in n for n in s.notes())


# --- stopping ------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_waits_for_the_last_turn() -> None:
    stream = FakeStream({1: [start(1, 0)]}, on_end=[complete(1, "And that's it.", 600)])
    s = Setup(FakeASR(stream))
    s.bridge.start()
    await until(lambda: s.bridge.streaming)
    await s.frames(2)
    await s.bridge.stop()
    assert stream.ended and s.turns()[0]["text"] == "And that's it."
    assert s.bridge.state == "idle" and not s.bridge.streaming


@pytest.mark.asyncio
async def test_stop_sends_the_last_chunk() -> None:
    asr = FakeASR(ASRError("policy", code=1008), transcriptions=(chunk_reply((0, 900, "Bye.")),))
    s = Setup(asr)
    s.bridge.start()
    await until(lambda: s.bridge.state == "chunked")
    await s.frames(20)  # 1.6 s: worth sending
    await s.bridge.stop()
    assert len(asr.chunks) == 1 and s.turns()[0]["text"] == "Bye."


# --- the audio socket, end to end ------------------------------------------------------------------------------


def make_client(tmp_path: Path, asr: FakeASR | None) -> TestClient:
    write_quiet_streak(tmp_path)
    app = FastAPI()
    app.include_router(router)
    modes = {Mode.CODING: CodingMode(ProblemBank.load(tmp_path))}
    model = RoleModel("Yes, it can be empty. What would you return then?")
    app.state.hub = SessionHub(MemoryStore(), modes, model=model, asr=asr)
    return TestClient(app)


@pytest.fixture
def asked_stream() -> FakeStream:
    return FakeStream(
        {
            1: [start(1, 0), partial("can the readings", 300)],
            3: [complete(1, "Can the readings list be empty?", 900)],
        }
    )


@pytest.fixture
def client(tmp_path: Path, asked_stream: FakeStream) -> Iterator[TestClient]:
    with make_client(tmp_path, FakeASR(asked_stream)) as test_client:
        yield test_client


def receive_until(ws: Any, done: Callable[[dict[str, Any]], bool], limit: int = 60) -> dict[str, Any]:
    for _ in range(limit):
        message = ws.receive_json()
        if done(message):
            return message
    raise AssertionError("expected message never arrived")


def new_session(client: TestClient, **config: Any) -> str:
    body = {"mode": "coding", "problem_slug": "quiet-streak", **config}
    return client.post("/api/sessions", json=body).json()["id"]


def test_a_spoken_question_held_on_ask_gets_the_interviewers_answer(
    client: TestClient, asked_stream: FakeStream
) -> None:
    sid = new_session(client)
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        receive_until(ws, lambda m: m["type"] == "session.state" and m["phase"] == "clarify")
        with client.websocket_connect(f"/ws/sessions/{sid}/audio") as audio:
            audio.send_text(json.dumps({"type": "start"}))
            bridge = client.app.state.hub.runtimes[sid].voice
            client.portal.call(until, lambda: bridge.streaming)
            audio.send_text(json.dumps({"type": "ask", "holding": True}))
            for _ in range(4):
                audio.send_bytes(FRAME)
            audio.send_text(json.dumps({"type": "ask", "holding": False}))
            caption = receive_until(ws, lambda m: m["type"] == "transcript.update" and m["turn"]["final"])
            reply = receive_until(
                ws, lambda m: m["type"] == "interviewer.message" and m["intervention"]["trigger"] == "asked"
            )
    assert (caption["turn"]["text"], caption["turn"]["source"]) == (
        "Can the readings list be empty?",
        "voice",
    )
    assert reply["intervention"]["text"] == "Yes, it can be empty. What would you return then?"
    assert len(asked_stream.frames) >= 3


@pytest.mark.parametrize(
    ("config", "asr", "code"),
    [
        ({}, None, 4503),  # no transcription configured (no key)
        ({"voice": False}, "fake", 4403),  # the session was created without voice
    ],
)
def test_the_audio_socket_refuses_when_voice_is_off(
    tmp_path: Path, config: dict[str, Any], asr: str | None, code: int
) -> None:
    with make_client(tmp_path, FakeASR(FakeStream()) if asr else None) as client:
        sid = new_session(client, **config)
        with (
            pytest.raises(WebSocketDisconnect) as closed,
            client.websocket_connect(f"/ws/sessions/{sid}/audio") as audio,
        ):
            audio.receive_bytes()
        assert closed.value.code == code
        with (
            pytest.raises(WebSocketDisconnect) as unknown,
            client.websocket_connect("/ws/sessions/nope/audio") as audio,
        ):
            audio.receive_bytes()
        assert unknown.value.code == 4404


def test_a_second_tab_takes_the_microphone(client: TestClient) -> None:
    sid = new_session(client)
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        receive_until(ws, lambda m: m["type"] == "session.state" and m["phase"] == "clarify")
        with client.websocket_connect(f"/ws/sessions/{sid}/audio") as first:
            first.send_text(json.dumps({"type": "start"}))
            with client.websocket_connect(f"/ws/sessions/{sid}/audio") as second:
                second.send_text(json.dumps({"type": "start"}))
                with pytest.raises(WebSocketDisconnect) as taken:
                    first.receive_bytes()
    assert taken.value.code == 4409
