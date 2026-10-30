"""Wrap-up answers (PLAN §10.1): typed ones move on at once, spoken ones after a quiet gap.

The session clock is moved by hand and the voice bridge's events are fed straight in, as Muse Voice sends them.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from crucible.coding.problems import ProblemBank
from crucible.coding.session import ANSWER_GAP_MS, ANSWER_POLL_S, WRAP_UP_LIMIT_S, CodingMode
from crucible.contracts.common import Phase
from crucible.contracts.events import InterventionLevel, TimelineEvent, TimelineKind
from crucible.contracts.ws import ChatSend
from crucible.engine.voice import VoiceBridge
from crucible.models.asr import parse_event
from tests.engine.test_voice import Clock, FakeASR, FakeStream, Tab, complete, start, until
from tests.factories import runtime, write_quiet_streak

GAP_S = ANSWER_GAP_MS / 1000


class Wrap:
    """A coding session in its wrap-up, with the first question out."""

    def __init__(self, tmp_path: Path) -> None:
        write_quiet_streak(tmp_path)
        self.clock = Clock()
        self.rt = runtime(monotonic=self.clock)
        self.rt.session.phase = Phase.SETUP
        self.rt.controller = CodingMode(ProblemBank.load(tmp_path))()
        self.bridge = VoiceBridge(self.rt, FakeASR(FakeStream()))  # never started: events go in by hand
        self.connection = self.rt.add(Tab())
        self.turn = 0

    async def open(self) -> None:
        await self.rt.controller.on_start(self.rt)
        await self.rt.set_phase(Phase.CODING, "started coding")
        await self.rt.set_phase(Phase.WRAP_UP, "candidate is done")
        await until(lambda: len(self.questions()) == 1)

    async def speech_start(self) -> None:
        self.turn += 1
        await self._voice(start(self.turn, self.rt.now_ms()))

    async def speech_complete(self, text: str) -> None:
        await self._voice(complete(self.turn, text, self.rt.now_ms()))

    async def says(self, text: str) -> None:
        """One spoken turn, about a second long, ended by a pause."""
        await self.speech_start()
        self.clock.now += 1.0
        await self.speech_complete(text)

    async def types(self, text: str) -> None:
        await self.rt.handle(self.connection, ChatSend(type="chat.send", text=text))

    async def wait(self, seconds: float) -> None:
        """`seconds` pass on the session clock (silence), then the controller gets a few looks at it."""
        self.clock.now += seconds
        await asyncio.sleep(3 * ANSWER_POLL_S)

    def questions(self) -> list[TimelineEvent]:
        events = self.rt.timeline.tail([TimelineKind.INTERVENTION])
        return [e for e in events if e.payload["level"] == InterventionLevel.QUESTION]

    def said(self, text_part: str) -> bool:
        events = self.rt.timeline.tail([TimelineKind.INTERVENTION])
        return any(text_part in e.payload["text"] for e in events)

    async def _voice(self, raw: dict[str, Any]) -> None:
        event = parse_event(json.dumps(raw))
        assert event is not None
        await self.bridge._on_event(event)


@pytest.fixture
async def wrap(tmp_path: Path) -> AsyncIterator[Wrap]:
    session = Wrap(tmp_path)
    await session.open()
    yield session
    await session.rt.close()


async def test_a_spoken_answer_in_two_turns_gets_one_question_after_the_gap(wrap: Wrap) -> None:
    await wrap.says("It's O of n time")
    await wrap.wait(1.5)  # the pause Muse Voice ends a turn at
    assert len(wrap.questions()) == 1
    await wrap.says("and O of one space")
    answered_ms = wrap.rt.now_ms()
    await wrap.wait(GAP_S - 0.3)
    assert len(wrap.questions()) == 1
    await wrap.wait(0.4)
    await until(lambda: len(wrap.questions()) == 2)
    assert wrap.questions()[1].t >= answered_ms + ANSWER_GAP_MS
    await wrap.wait(GAP_S + 1)
    assert len(wrap.questions()) == 2


async def test_speech_resuming_within_the_gap_holds_the_question(wrap: Wrap) -> None:
    await wrap.says("It's O of n time")
    await wrap.wait(2.0)
    await wrap.speech_start()  # talking again; the turn isn't final yet
    await wrap.wait(5.0)  # long past the first turn's gap
    assert len(wrap.questions()) == 1
    await wrap.speech_complete("and O of one space, since I only keep two counters")
    await wrap.wait(GAP_S - 0.3)
    assert len(wrap.questions()) == 1
    await wrap.wait(0.4)
    await until(lambda: len(wrap.questions()) == 2)


async def test_a_typed_answer_moves_on_at_once(wrap: Wrap) -> None:
    await wrap.types("O(n) time, O(1) space.")
    await until(lambda: len(wrap.questions()) == 2)
    assert wrap.questions()[1].t == wrap.rt.now_ms()  # the session clock never moved


async def test_a_typed_answer_after_a_spoken_one_moves_on_once(wrap: Wrap) -> None:
    await wrap.says("It's O of n time")
    await wrap.types("and O(1) space")
    await until(lambda: len(wrap.questions()) == 2)
    await wrap.wait(GAP_S + 1)
    # The spoken half doesn't also move on from the next question (the last one, so that would close).
    assert len(wrap.questions()) == 2 and wrap.rt.live


async def test_two_answers_at_once_move_on_once(wrap: Wrap) -> None:
    await wrap.types("O(n) time")
    await wrap.types("O(1) space")  # before the controller's step for the first one has run
    await until(lambda: len(wrap.questions()) == 2)
    await asyncio.sleep(3 * ANSWER_POLL_S)
    assert len(wrap.questions()) == 2 and wrap.rt.live


async def test_the_last_spoken_answer_closes_after_the_gap(wrap: Wrap) -> None:
    await wrap.types("O(n) time, O(1) space.")
    await until(lambda: len(wrap.questions()) == 2)
    await wrap.says("I'd keep the running count")
    await wrap.wait(1.0)
    assert wrap.rt.live
    await wrap.wait(GAP_S)
    await until(lambda: not wrap.rt.live)
    assert wrap.said("end of the interview")


async def test_the_wrap_up_limit_still_ends_the_session_while_the_candidate_talks(wrap: Wrap) -> None:
    await wrap.says("It's O of n time")
    await wrap.speech_start()  # and keeps talking
    wrap.clock.now += WRAP_UP_LIMIT_S
    await until(lambda: not wrap.rt.live)
    ended = [
        e.payload for e in wrap.rt.timeline.tail([TimelineKind.PHASE]) if e.payload["to_phase"] == "ended"
    ]
    assert [p["reason"] for p in ended] == ["wrap-up time limit"]
    assert wrap.said("end of the interview") and len(wrap.questions()) == 1
