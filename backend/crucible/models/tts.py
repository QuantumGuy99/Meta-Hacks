"""Voice output: the interviewer's lines read aloud by ElevenLabs (PLAN §14.7).

Meta has no text-to-speech model, so this is the one call that isn't to Meta, and it's output only: it sees the
interviewer's own lines after the leak guard, never code, tests, the rubric or the candidate. Streaming endpoint
checked against elevenlabs.io/docs/api-reference/text-to-speech/stream on 2026-11-03.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import OrderedDict
from collections.abc import AsyncIterator

import httpx

from crucible.config import Settings
from crucible.models.registry import TTS_MODEL

logger = logging.getLogger(__name__)

STREAM_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
OUTPUT_FORMAT = "mp3_44100_128"
MEDIA_TYPE = "audio/mpeg"
CONNECT_TIMEOUT_S = 2.0
FIRST_AUDIO_TIMEOUT_S = 3.0  # the browser gives up at 1.5 s and speaks the line itself (lib/tts.ts)
READ_TIMEOUT_S = 10.0  # between chunks, once audio is flowing
MAX_TEXT_CHARS = 1_000  # interviewer lines are a sentence or two; nothing longer is read out
CACHE_LINES = 64  # canned lines (the greeting, phase lines) repeat in every session: say them once
# A little below the default stability sounds more conversational; the rest are ElevenLabs' defaults.
VOICE_SETTINGS = {"stability": 0.4, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True}


class SpeechUnavailable(Exception):
    """The voice service didn't start speaking: the browser voice reads the line instead."""


class Speech:
    """One ElevenLabs voice. `open()` raises before any audio is sent, so a failure is still a clean HTTP error."""

    def __init__(self, api_key: str, voice_id: str, client: httpx.AsyncClient | None = None) -> None:
        self._key, self._voice = api_key, voice_id
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(READ_TIMEOUT_S, connect=CONNECT_TIMEOUT_S)
        )
        self._cache: OrderedDict[str, bytes] = OrderedDict()

    async def open(self, text: str) -> AsyncIterator[bytes]:
        """The audio for `text`, its first chunk already received. Raises SpeechUnavailable otherwise."""
        line = speakable(text)[:MAX_TEXT_CHARS]
        if not line:
            raise SpeechUnavailable("nothing to say")
        if (cached := self._cache.get(line)) is not None:
            self._cache.move_to_end(line)
            return _once(cached)
        started = time.monotonic()
        request = self._client.build_request(
            "POST",
            STREAM_URL.format(voice_id=self._voice),
            params={"output_format": OUTPUT_FORMAT},
            headers={"xi-api-key": self._key},
            json={"text": line, "model_id": TTS_MODEL, "voice_settings": VOICE_SETTINGS},
        )
        response: httpx.Response | None = None
        try:
            async with asyncio.timeout(FIRST_AUDIO_TIMEOUT_S):
                response = await self._client.send(request, stream=True)
                if response.status_code != 200:
                    await response.aread()
                    raise SpeechUnavailable(f"ElevenLabs answered {response.status_code}")
                chunks = response.aiter_bytes()
                first = await anext(chunks)
        except (TimeoutError, httpx.HTTPError, StopAsyncIteration, SpeechUnavailable) as exc:
            if response is not None:
                await response.aclose()
            raise SpeechUnavailable(str(exc) or type(exc).__name__) from exc
        logger.info(
            "speech started: %d chars, first audio after %d ms",
            len(line),
            (time.monotonic() - started) * 1000,
        )
        return self._rest(line, response, chunks, first)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _rest(
        self, line: str, response: httpx.Response, chunks: AsyncIterator[bytes], first: bytes
    ) -> AsyncIterator[bytes]:
        parts = [first]
        try:
            yield first
            while True:
                async with asyncio.timeout(READ_TIMEOUT_S):
                    chunk = await anext(chunks)
                parts.append(chunk)
                yield chunk
        except StopAsyncIteration:
            self._remember(line, b"".join(parts))
        except (TimeoutError, httpx.HTTPError):
            logger.warning(
                "speech stream cut off after %d bytes", sum(map(len, parts))
            )  # the browser stops there
        finally:
            await response.aclose()

    def _remember(self, line: str, audio: bytes) -> None:
        self._cache[line] = audio
        while len(self._cache) > CACHE_LINES:
            self._cache.popitem(last=False)


def speech_from(settings: Settings) -> Speech | None:
    """The configured voice, or None: the browser voice speaks every line."""
    return Speech(settings.TTS_API_KEY, settings.TTS_VOICE_ID) if settings.has_tts else None


def speakable(text: str) -> str:
    """The line as it should sound: code blocks skipped, inline code and emphasis markers dropped."""
    text = re.sub(r"```[\s\S]*?(```|$)", " ", text)
    text = re.sub(r"[`*~#>]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


async def _once(audio: bytes) -> AsyncIterator[bytes]:
    yield audio
