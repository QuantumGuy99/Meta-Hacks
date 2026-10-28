"""VoiceBridge: the candidate's microphone → Muse Voice Transcribe → the transcript (PLAN §8.3, §9.7).

One per session, fed by the audio socket. Realtime first: partials go to the tabs as `transcript.update` (never
stored) and completed turns become final `TranscriptTurn`s on the timeline, which the analyzer and the modes react
to. A turn spoken while the candidate holds **Ask** is a question to the interviewer. After 3 realtime failures it
falls back to transcribing 10 s WAV chunks; if that fails too, voice is off and the candidate is told to use chat.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from crucible.contracts.events import ModelActivity, TimelineKind, TranscriptTurn
from crucible.contracts.ws import ErrorMsg, TranscriptUpdate
from crucible.engine.activity import LISTENING, TRANSCRIBING, VOICE
from crucible.engine.ids import new_id
from crucible.models.asr import (
    BYTES_PER_MS,
    ASRError,
    ASREvent,
    ErrorEvent,
    Partial,
    SpeechComplete,
    SpeechEnd,
    SpeechStart,
    Transcription,
)

if TYPE_CHECKING:
    from crucible.engine.hub import SessionRuntime

logger = logging.getLogger(__name__)

MAX_REALTIME_FAILURES = 3  # in a row; then the chunked fallback (§9.7)
BACKOFF_S = 0.5  # doubled per failure
RATE_LIMITED_BACKOFF_S = 5  # close code 1013
CLOSE_REJECTED = 1008  # a bad request or a streaming-policy failure: retrying the same stream fails again
CLOSE_FAILED = 1011
CLOSE_RATE_LIMITED = 1013
SESSION_CAP = "Max session duration"  # 1011 at the 60-minute cap: reconnect, not a failure
STOP_DRAIN_S = 5  # after endStream, how long to wait for the last turns
CHUNK_BYTES = 10_000 * BYTES_PER_MS  # 10 s chunks in the fallback
MIN_CHUNK_BYTES = 1_000 * BYTES_PER_MS  # a last chunk under 1 s isn't worth a request
MAX_CHUNK_FAILURES = 2
ASK_GRACE_MS = 500  # audio and session clocks can disagree by a few hundred ms
ASK_SHARE = 0.5  # a turn is a question when Ask was held for at least half of it
UNAVAILABLE = "Voice isn't available right now. Please use the chat."

VoiceState = Literal["idle", "realtime", "chunked", "unavailable"]


class AudioControl(BaseModel):
    """A text frame on the audio socket (§8.3): start, stop, or the Ask button pressed or released."""

    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["start", "stop", "ask"]
    holding: bool = False


class Stream(Protocol):
    """One realtime transcription session (`crucible.models.asr.RealtimeStream`)."""

    session_id: str

    async def send_audio(self, frame: bytes) -> None: ...
    async def end_stream(self) -> None: ...
    def events(self) -> AsyncIterator[ASREvent]: ...
    async def close(self) -> None: ...


class Transcriber(Protocol):
    """Both transcription endpoints (`crucible.models.asr.MuseASR`)."""

    async def open_stream(self) -> Stream: ...
    async def transcribe(self, pcm: bytes) -> Transcription: ...


@dataclass(slots=True)
class _Turn:
    id: str
    start_ms: int
    end_ms: int | None = None


class VoiceBridge:
    def __init__(
        self,
        rt: SessionRuntime,
        asr: Transcriber,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._rt = rt
        self._asr = asr
        self._sleep = sleep
        self.state: VoiceState = "idle"
        self._stopping = False
        self._failures = 0
        self._supervisor: asyncio.Task[None] | None = None
        # The open realtime stream, and the session time its audio started (audioProcessedMs counts from there).
        self._stream: Stream | None = None
        self._stream_t0: int | None = None
        self._turns: dict[int, _Turn] = {}
        self._current: int | None = None  # the turn the latest speechStart opened; partials belong to it
        self._chunk = bytearray()
        self._chunk_t0: int | None = None
        self._chunk_failures = 0
        self._uploads: set[asyncio.Task[None]] = set()
        self._asks: list[tuple[int, int | None]] = []  # (pressed, released) in session ms

    @property
    def streaming(self) -> bool:
        """A realtime stream is open and taking audio."""
        return self._stream is not None

    # --- the audio socket ---------------------------------------------------------------------------------------

    def start(self) -> None:
        """The candidate turned the mic on: open realtime transcription (unless voice already failed)."""
        if self.state != "idle":
            return
        self._stopping = False
        self.state = "realtime"
        self._supervisor = asyncio.create_task(self._run_realtime(), name=f"voice-{self._rt.session.id}")

    async def audio(self, frame: bytes) -> None:
        """One 80 ms PCM frame. Forwarded at once: audio that arrives while reconnecting is dropped, never
        buffered and burst later (Meta closes a stream that runs ahead of real time)."""
        now = self._rt.now_ms()
        if self.state == "chunked":
            if self._chunk_t0 is None:
                self._chunk_t0 = now - len(frame) // BYTES_PER_MS
            self._chunk += frame
            if len(self._chunk) >= CHUNK_BYTES:
                self._send_chunk()
            return
        stream = self._stream
        if self.state != "realtime" or stream is None:
            return
        if self._stream_t0 is None:
            self._stream_t0 = now - len(frame) // BYTES_PER_MS  # this frame's audio started a frame ago
        with contextlib.suppress(ASRError):  # the reader sees the close and reconnects
            await stream.send_audio(frame)

    def ask(self, holding: bool) -> None:
        """The Ask button: a turn spoken while it's held is a question to the interviewer (§9.7)."""
        now = self._rt.now_ms()
        open_window = bool(self._asks) and self._asks[-1][1] is None
        if holding and not open_window:
            self._asks = [w for w in self._asks if w[1] is None or now - w[1] < 60_000]
            self._asks.append((now, None))
        elif not holding and open_window:
            self._asks[-1] = (self._asks[-1][0], now)

    async def stop(self) -> None:
        """The mic turned off or its socket closed: send what's left, then stop until the next `start`."""
        self._stopping = True
        stream, supervisor = self._stream, self._supervisor
        if stream is not None and supervisor is not None:
            await stream.end_stream()
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(STOP_DRAIN_S):
                    await asyncio.shield(supervisor)  # the reader records the last turns, then sees 1000
        await self._cancel()
        if self.state == "chunked" and len(self._chunk) >= MIN_CHUNK_BYTES:
            self._send_chunk()
        self._chunk.clear()
        self._chunk_t0 = None
        if self._uploads:
            await asyncio.gather(*self._uploads, return_exceptions=True)
        if self.state == "realtime":
            self.state = "idle"
        await self._rt.set_interviewer_state("idle")

    async def close(self) -> None:
        """The runtime is closing: stop at once, without waiting for the last turns."""
        self._stopping = True
        await self._cancel()
        for task in list(self._uploads):
            task.cancel()
        self._uploads.clear()

    # --- realtime -------------------------------------------------------------------------------------------------

    async def _run_realtime(self) -> None:
        while not self._stopping:
            try:
                stream = await self._asr.open_stream()
            except ASRError as exc:
                if await self._failed(exc):
                    continue
                return
            self._stream, self._stream_t0, self._turns, self._current = stream, None, {}, None
            failure: ASRError | None = None
            try:
                async for event in stream.events():
                    await self._on_event(event)
            except ASRError as exc:
                failure = exc
            finally:
                self._stream = None
            # A close with 1000 after our endStream ends the loop; one we didn't ask for opens a new stream.
            if failure is not None and not await self._failed(failure):
                return

    async def _failed(self, exc: ASRError) -> bool:
        """Handle a realtime failure; True to reconnect."""
        if self._stopping or not self._rt.live:
            return False
        if exc.code == CLOSE_FAILED and SESSION_CAP in exc.reason:
            await self._rt.note("info", "realtime transcription hit its 60-minute cap; reconnecting")
            return True
        logger.warning("voice in %s: %s", self._rt.session.id, exc)
        self._failures += 1
        if exc.code == CLOSE_REJECTED or self._failures >= MAX_REALTIME_FAILURES:
            await self._rt.note(
                "warning", f"realtime transcription failed ({exc}); transcribing 10 s chunks instead"
            )
            self.state = "chunked"
            return False
        await self._rt.note("info", f"realtime transcription dropped ({exc}); reconnecting")
        await self._sleep(
            RATE_LIMITED_BACKOFF_S
            if exc.code == CLOSE_RATE_LIMITED
            else BACKOFF_S * 2 ** (self._failures - 1)
        )
        return not self._stopping

    async def _on_event(self, event: ASREvent) -> None:
        self._failures = 0  # the stream works
        t0 = self._stream_t0 or 0
        match event:
            case SpeechStart():
                turn = self._turns[event.turn_id] = _Turn(new_id(), t0 + event.audio_ms)
                self._current = event.turn_id
                self._rt.heard_speech()
                await self._rt.set_interviewer_state("listening")
                await self._activity(turn.id, LISTENING, "started")
            case Partial():
                turn = self._open_turn(t0 + event.audio_ms)
                self._rt.heard_speech()
                partial = _turn(turn.id, event.text, turn.start_ms, t0 + event.audio_ms, final=False)
                await self._rt.broadcast(TranscriptUpdate(type="transcript.update", turn=partial))
            case SpeechEnd():
                if event.turn_id in self._turns:
                    self._turns[event.turn_id].end_ms = t0 + event.audio_ms
            case SpeechComplete():
                turn = self._turns.pop(event.turn_id, None) or _Turn(new_id(), t0 + event.audio_ms)
                if self._current == event.turn_id:
                    self._current = None
                end_ms = turn.end_ms or t0 + event.audio_ms
                await self._final(turn.id, event.text, turn.start_ms, end_ms)
                await self._activity(turn.id, LISTENING, "done", latency_ms=max(0, end_ms - turn.start_ms))
                if not self._turns:
                    await self._rt.set_interviewer_state("idle")
            case ErrorEvent():
                await self._rt.note("warning", f"transcription error: {event.message}")

    def _open_turn(self, now_ms: int) -> _Turn:
        """The turn a partial belongs to; one is opened if a partial arrives before its speechStart."""
        if self._current is None or self._current not in self._turns:
            self._current = min(self._turns, default=0) - 1  # below any server turn id
            self._turns[self._current] = _Turn(new_id(), now_ms)
        return self._turns[self._current]

    # --- the chunked fallback ---------------------------------------------------------------------------------

    def _send_chunk(self) -> None:
        pcm, t0 = bytes(self._chunk), self._chunk_t0 or 0
        self._chunk.clear()
        self._chunk_t0 = None
        task = asyncio.create_task(self._transcribe(pcm, t0), name=f"voice-chunk-{self._rt.session.id}")
        self._uploads.add(task)
        task.add_done_callback(self._uploads.discard)

    async def _transcribe(self, pcm: bytes, t0: int) -> None:
        call_id, sent_ms = new_id(), self._rt.now_ms()
        await self._activity(call_id, TRANSCRIBING, "started")
        try:
            result = await self._asr.transcribe(pcm)
        except ASRError as exc:
            await self._activity(call_id, TRANSCRIBING, "failed", latency_ms=self._rt.now_ms() - sent_ms)
            self._chunk_failures += 1
            logger.warning("voice chunk in %s: %s", self._rt.session.id, exc)
            if self._chunk_failures >= MAX_CHUNK_FAILURES and self.state != "unavailable":
                await self._unavailable(exc)
            return
        except Exception:  # task boundary: a bug here must not leave the task's error unseen
            logger.exception("voice chunk in %s failed", self._rt.session.id)
            return
        self._chunk_failures = 0
        await self._activity(call_id, TRANSCRIBING, "done", latency_ms=self._rt.now_ms() - sent_ms)
        # A zero-length turn is the service repeating the end of the previous one (seen live, PLAN §23 V1).
        turns = [(t.text, t.start_ms, t.end_ms) for t in result.turns if t.end_ms > t.start_ms]
        if not turns and result.text.strip():
            turns = [(result.text, 0, result.audio_ms)]
        for text, start, end in turns:
            await self._final(new_id(), text, t0 + start, t0 + end)

    async def _unavailable(self, exc: ASRError) -> None:
        self.state = "unavailable"
        self._chunk.clear()
        await self._rt.note("error", f"voice is unavailable ({exc}); the candidate was asked to use the chat")
        await self._rt.broadcast(
            ErrorMsg(type="error", code="voice_unavailable", message=UNAVAILABLE, retryable=False)
        )

    # --- turns ------------------------------------------------------------------------------------------------------

    async def _final(self, turn_id: str, text: str, start_ms: int, end_ms: int) -> None:
        """A completed turn: on the timeline first (the analyzer and the mode react), then to every tab."""
        text = text.strip()
        if not text:
            return
        turn = _turn(turn_id, text, start_ms, end_ms, final=True)
        await self._rt.record(TimelineKind.TRANSCRIPT, turn)
        await self._rt.broadcast(TranscriptUpdate(type="transcript.update", turn=turn))
        if self._asked(turn.start_ms, turn.end_ms):
            self._rt.asked(text)

    async def _activity(
        self,
        call_id: str,
        task: str,
        status: Literal["started", "done", "failed"],
        latency_ms: int | None = None,
    ) -> None:
        """Muse Voice on the "Under the hood" strip: listening while the candidate talks, or a chunk's request."""
        activity = ModelActivity(
            call_id=call_id,
            t=self._rt.now_ms(),
            model_name=VOICE,
            task=task,
            status=status,
            latency_ms=latency_ms,
        )
        await self._rt.show_activity(activity)

    def _asked(self, start_ms: int, end_ms: int) -> bool:
        """Was Ask held for most of this turn? Any overlap isn't enough: the candidate may let go of Ask and keep
        talking, and the transcriber's turn times can be a few hundred ms off (measured live, PLAN §23 V1)."""
        length = max(1, end_ms - start_ms)
        for pressed, released in self._asks:
            held_from = pressed - ASK_GRACE_MS
            held_to = (released + ASK_GRACE_MS) if released is not None else end_ms
            if min(end_ms, held_to) - max(start_ms, held_from) >= ASK_SHARE * length:
                return True
        return False

    async def _cancel(self) -> None:
        supervisor, self._supervisor = self._supervisor, None
        if supervisor is not None and not supervisor.done():
            supervisor.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await supervisor
        stream, self._stream = self._stream, None
        if stream is not None:
            with contextlib.suppress(Exception):  # it may already be closed
                await stream.close()


def _turn(turn_id: str, text: str, start_ms: int, end_ms: int, *, final: bool) -> TranscriptTurn:
    start = max(0, start_ms)
    return TranscriptTurn(
        turn_id=turn_id,
        speaker="candidate",
        text=text,
        start_ms=start,
        end_ms=max(start, end_ms),
        final=final,
        source="voice",
    )
