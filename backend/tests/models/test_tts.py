"""The ElevenLabs voice (PLAN §14.7) against a fake HTTP transport: what's sent, streaming, failures, the cache."""

import asyncio
import json

import httpx
import pytest

from crucible.config import Settings
from crucible.models import tts
from crucible.models.registry import TTS_MODEL
from crucible.models.tts import Speech, SpeechUnavailable, speakable, speech_from

AUDIO = [b"ID3-first", b"-second", b"-third"]


class Upstream:
    """Records requests and answers like ElevenLabs' streaming endpoint."""

    def __init__(self, status: int = 200, delay_s: float = 0.0) -> None:
        self.status, self.delay_s = status, delay_s
        self.requests: list[httpx.Request] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        await asyncio.sleep(self.delay_s)
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": {"status": "invalid_api_key"}})
        return httpx.Response(200, content=_stream(AUDIO), headers={"content-type": "audio/mpeg"})

    def speech(self) -> Speech:
        return Speech("test-key", "voice-1", httpx.AsyncClient(transport=httpx.MockTransport(self)))


async def _stream(chunks: list[bytes]):
    for chunk in chunks:
        yield chunk


async def heard(speech: Speech, text: str) -> bytes:
    return b"".join([chunk async for chunk in await speech.open(text)])


async def test_a_line_is_streamed_in_the_configured_voice_and_model() -> None:
    upstream = Upstream()
    assert await heard(upstream.speech(), "What does `swings` count?") == b"".join(AUDIO)
    [request] = upstream.requests
    assert request.url.path == "/v1/text-to-speech/voice-1/stream"
    assert request.url.params["output_format"] == tts.OUTPUT_FORMAT
    assert request.headers["xi-api-key"] == "test-key"
    body = json.loads(request.content)
    assert body["text"] == "What does swings count?" and body["model_id"] == TTS_MODEL


async def test_a_line_said_before_comes_from_the_cache() -> None:
    upstream = Upstream()
    speech = upstream.speech()
    await heard(speech, "Here's your problem.")
    assert await heard(speech, "Here's your problem.") == b"".join(AUDIO)
    assert len(upstream.requests) == 1


async def test_an_error_from_the_service_is_unavailable_before_any_audio() -> None:
    with pytest.raises(SpeechUnavailable, match="401"):
        await Upstream(status=401).speech().open("Hello there.")


async def test_no_first_audio_in_time_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tts, "FIRST_AUDIO_TIMEOUT_S", 0.05)
    with pytest.raises(SpeechUnavailable):
        await Upstream(delay_s=1.0).speech().open("Hello there.")


async def test_a_connection_failure_is_unavailable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    speech = Speech("k", "v", httpx.AsyncClient(transport=httpx.MockTransport(refuse)))
    with pytest.raises(SpeechUnavailable):
        await speech.open("Hello there.")


async def test_nothing_to_say_is_not_sent() -> None:
    upstream = Upstream()
    with pytest.raises(SpeechUnavailable):
        await upstream.speech().open("```python\nx = 1\n```")
    assert upstream.requests == []


def test_code_and_markers_are_not_read_out() -> None:
    assert speakable("Look at **line 3**:\n```py\nreturn x\n```  then `n`.") == "Look at line 3: then n."


def test_no_voice_without_both_settings() -> None:
    assert speech_from(Settings(TTS_API_KEY="k", TTS_VOICE_ID="")) is None
    assert speech_from(Settings(TTS_API_KEY="", TTS_VOICE_ID="v")) is None
    assert speech_from(Settings(TTS_API_KEY="k", TTS_VOICE_ID="v")) is not None
