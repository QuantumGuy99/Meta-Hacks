"""GET /api/sessions/{id}/speech/{intervention_id} (PLAN §14.7): only a line the session showed and marked to speak
is read aloud, and anything else is an error the browser answers with its own voice."""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crucible.contracts.events import (
    Intervention,
    InterventionLevel,
    InterventionTrigger,
    TimelineEvent,
    TimelineKind,
)
from crucible.engine.api import _spoken_line
from crucible.models.tts import MEDIA_TYPE, SpeechUnavailable
from tests.engine.test_first_nudge import join, make_client, receive_until
from tests.factories import FakeModel, analysis


class FakeSpeech:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.said: list[str] = []

    async def open(self, text: str) -> AsyncIterator[bytes]:
        if self.fail:
            raise SpeechUnavailable("down")
        self.said.append(text)
        return self._audio()

    async def _audio(self) -> AsyncIterator[bytes]:
        yield b"mp3-1"
        yield b"mp3-2"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with make_client(tmp_path, FakeModel(analysis())) as test_client:
        yield test_client


def first_line(client: TestClient, **config: object) -> tuple[str, dict]:
    """A session, and the problem's presentation line it spoke."""
    sid, socket = join(client, **config)
    with socket as ws:
        ws.send_json({"type": "hello", "client_now_ms": 0})
        message = receive_until(ws, lambda m: m["type"] == "interviewer.message")
    return sid, message["intervention"]


def test_a_spoken_line_streams_as_audio(client: TestClient) -> None:
    client.app.state.speech = speech = FakeSpeech()
    sid, line = first_line(client)
    response = client.get(f"/api/sessions/{sid}/speech/{line['id']}")
    assert response.status_code == 200
    assert response.headers["content-type"] == MEDIA_TYPE and response.content == b"mp3-1mp3-2"
    assert speech.said == [line["text"]]  # the text comes from the timeline, never from the request


def test_unknown_lines_and_sessions_are_404(client: TestClient) -> None:
    client.app.state.speech = FakeSpeech()
    sid, _ = first_line(client)
    assert client.get(f"/api/sessions/{sid}/speech/nope").json()["error"]["code"] == "line_not_found"
    assert client.get("/api/sessions/nope/speech/x").status_code == 404


def test_without_a_voice_service_the_browser_speaks(client: TestClient) -> None:
    client.app.state.speech = None
    sid, line = first_line(client)
    response = client.get(f"/api/sessions/{sid}/speech/{line['id']}")
    assert response.status_code == 503 and response.json()["error"]["code"] == "voice_unavailable"


def test_a_failing_voice_service_is_503(client: TestClient) -> None:
    client.app.state.speech = FakeSpeech(fail=True)
    sid, line = first_line(client)
    assert client.get(f"/api/sessions/{sid}/speech/{line['id']}").status_code == 503


def line_event(seq: int, *, speak: bool = True, suppressed: bool = False) -> TimelineEvent:
    payload = Intervention(
        id=f"i{seq}",
        t=seq,
        trigger=InterventionTrigger.MISSED_STEP,
        level=InterventionLevel.QUESTION,
        text="What should an empty list give you?",
        step_id="s1",
        speak=speak,
        suppressed=suppressed,
    )
    return TimelineEvent(
        seq=seq, t=seq, kind=TimelineKind.INTERVENTION, payload=payload.model_dump(mode="json")
    )


def test_only_shown_lines_marked_to_speak_are_read() -> None:
    events = [line_event(1), line_event(2, speak=False), line_event(3, suppressed=True)]
    assert _spoken_line(events, "i1") == "What should an empty list give you?"
    assert _spoken_line(events, "i2") is None and _spoken_line(events, "i3") is None
