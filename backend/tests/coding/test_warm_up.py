"""The warm-up before the problem (PLAN §3.1, §10.1): a greeting, the model's reaction and one follow-up, then the
problem with the full time. Typed answers move on at once, spoken ones after the quiet gap.

The session clock is moved by hand and the voice bridge's events are fed straight in, as Muse Voice sends them.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from crucible.coding.problems import ProblemBank
from crucible.coding.prompts import PHASE_LINES
from crucible.coding.session import ANSWER_GAP_MS, ANSWER_POLL_S, TIMER_TICK_S, CodingMode
from crucible.contracts.common import Phase
from crucible.contracts.events import TimelineEvent, TimelineKind
from crucible.contracts.ws import ChatSend, PhaseAdvance
from crucible.engine.report import NOT_HELP
from crucible.engine.voice import VoiceBridge
from crucible.models.asr import parse_event
from tests.engine.test_voice import Clock, FakeASR, FakeStream, Tab, complete, start, until
from tests.factories import FakeModel, runtime, write_quiet_streak

GAP_S = ANSWER_GAP_MS / 1000
FOLLOW_UP = {"text": "A compiler for a class, nice. What was the hardest part?"}
CLOSING = {"text": "That sounds like a fun challenge."}


class Intro:
    """A coding session at its start, before anything is said."""

    def __init__(self, tmp_path: Path, model: FakeModel | None, **mode: Any) -> None:
        write_quiet_streak(tmp_path)
        self.clock = Clock()
        self.model = model
        self.rt = runtime(model, monotonic=self.clock)
        self.rt.session.phase = Phase.SETUP
        self.rt.controller = CodingMode(ProblemBank.load(tmp_path), **mode)()
        self.bridge = VoiceBridge(self.rt, FakeASR(FakeStream()))  # never started: events go in by hand
        self.connection = self.rt.add(Tab())
        self.turn = 0

    async def open(self) -> None:
        await self.rt.controller.on_start(self.rt)

    async def says(self, text: str) -> None:
        """One spoken turn, about a second long, ended by a pause."""
        self.turn += 1
        await self._voice(start(self.turn, self.rt.now_ms()))
        self.clock.now += 1.0
        await self._voice(complete(self.turn, text, self.rt.now_ms()))

    async def types(self, text: str) -> None:
        await self.rt.handle(self.connection, ChatSend(type="chat.send", text=text))

    async def wait(self, seconds: float, ticks: int = 3) -> None:
        """`seconds` pass on the session clock (silence), then the controller gets a few looks at it."""
        self.clock.now += seconds
        await asyncio.sleep(ticks * ANSWER_POLL_S)

    def lines(self, trigger: str = "warmup") -> list[dict[str, Any]]:
        events: list[TimelineEvent] = self.rt.timeline.tail([TimelineKind.INTERVENTION])
        return [e.payload for e in events if e.payload["trigger"] == trigger]

    def model_heard(self) -> list[str]:
        """What the candidate said, as each warm-up reply call saw it (the analyzer shares the model later)."""
        assert self.model is not None
        calls = [m for m in self.model.calls if m[0]["content"].startswith("# interviewer_warmup")]
        return [json.loads(messages[-1]["content"])["candidate_said"] for messages in calls]

    async def _voice(self, raw: dict[str, Any]) -> None:
        event = parse_event(json.dumps(raw))
        assert event is not None
        await self.bridge._on_event(event)


async def opened(tmp_path: Path, model: FakeModel | None = None, **mode: Any) -> Intro:
    intro = Intro(tmp_path, model, **mode)
    await intro.open()
    return intro


def problem_presented(intro: Intro) -> bool:
    return any("Here's your problem" in line["text"] for line in intro.lines("phase"))


async def test_the_interviewer_greets_with_a_question_and_the_clock_waits(tmp_path: Path) -> None:
    intro = await opened(tmp_path)
    assert intro.rt.session.phase == Phase.INTRO
    [greeting] = intro.lines()
    assert greeting["level"] == "question" and greeting["text"] == PHASE_LINES["warmup_greeting"]
    await intro.wait(20)
    assert intro.rt.remaining_s() == intro.rt.session.time_limit_s
    await intro.rt.close()


async def test_two_typed_answers_get_a_follow_up_then_the_problem_with_the_full_time(tmp_path: Path) -> None:
    intro = await opened(tmp_path, FakeModel(FOLLOW_UP, CLOSING))
    limit = intro.rt.session.time_limit_s
    intro.clock.now += 12
    await intro.types("I'm a student, I've been building a small compiler for a class.")
    await until(lambda: len(intro.lines()) == 2)
    assert intro.lines()[1]["text"] == FOLLOW_UP["text"] and intro.lines()[1]["level"] == "question"
    intro.clock.now += 10
    await intro.types("Getting the parser to handle nested expressions.")
    await until(lambda: intro.rt.session.phase == Phase.CLARIFY and problem_presented(intro))
    assert intro.lines()[2]["text"] == CLOSING["text"] and intro.lines()[2]["level"] == "info"
    assert intro.model_heard() == [
        "I'm a student, I've been building a small compiler for a class.",
        "Getting the parser to handle nested expressions.",
    ]
    assert intro.rt.remaining_s() == limit  # the 22 s warm-up wasn't taken from the problem
    assert "20 minutes" in intro.lines("phase")[-1]["text"]
    await intro.rt.close()


async def test_a_spoken_answer_in_two_turns_gets_one_reply_after_the_gap(tmp_path: Path) -> None:
    intro = await opened(tmp_path, FakeModel(FOLLOW_UP, CLOSING))
    await intro.says("I'm working on a compiler")
    await intro.wait(1.5)  # the pause Muse Voice ends a turn at
    await intro.says("for my programming languages class")
    await intro.wait(GAP_S - 0.3)
    assert len(intro.lines()) == 1
    await intro.wait(0.4)
    await until(lambda: len(intro.lines()) == 2)
    assert intro.model_heard() == ["I'm working on a compiler for my programming languages class"]
    await intro.rt.close()


async def test_no_answer_moves_on_to_the_problem(tmp_path: Path) -> None:
    intro = await opened(tmp_path, FakeModel(FOLLOW_UP), warm_up_wait_s=5)
    await intro.wait(6, ticks=int(2 * TIMER_TICK_S / ANSWER_POLL_S) + 1)
    await until(lambda: intro.rt.session.phase == Phase.CLARIFY and problem_presented(intro))
    assert intro.lines()[-1]["text"] == PHASE_LINES["warmup_move_on"]
    assert intro.model_heard() == []
    await intro.rt.close()


async def test_no_follow_up_when_the_warm_up_is_almost_over(tmp_path: Path) -> None:
    intro = await opened(tmp_path, FakeModel(CLOSING), warm_up_limit_s=60, warm_up_wait_s=50)
    intro.clock.now += 12  # 48 s left, less than a follow-up's 50 s to answer
    await intro.types("I mostly write backend services at work.")
    await until(lambda: intro.rt.session.phase == Phase.CLARIFY and problem_presented(intro))
    assert [line["level"] for line in intro.lines()] == ["question", "info"]
    await intro.rt.close()


async def test_skip_intro_presents_the_problem_and_ends_the_warm_up(tmp_path: Path) -> None:
    intro = await opened(tmp_path, FakeModel(FOLLOW_UP))
    await intro.rt.handle(intro.connection, PhaseAdvance(type="phase.advance", to=Phase.CLARIFY))
    await until(lambda: problem_presented(intro))
    await intro.types("I'm a student working on a compiler.")
    await asyncio.sleep(3 * ANSWER_POLL_S)
    assert len(intro.lines()) == 1 and intro.model_heard() == []
    await intro.rt.close()


async def test_a_model_failure_falls_back_to_the_canned_follow_up(tmp_path: Path) -> None:
    intro = await opened(tmp_path, FakeModel(RuntimeError("down")))
    await intro.types("I build mobile apps.")
    await until(lambda: len(intro.lines()) == 2)
    assert intro.lines()[1]["text"] == PHASE_LINES["warmup_follow_up"]
    await intro.rt.close()


async def test_without_the_warm_up_the_problem_comes_first(tmp_path: Path) -> None:
    intro = await opened(tmp_path, warm_up=False)
    await until(lambda: problem_presented(intro))
    assert intro.rt.session.phase == Phase.CLARIFY and intro.lines() == []
    await intro.rt.close()


def test_the_warm_up_is_not_help() -> None:
    assert "warmup" in {t.value for t in NOT_HELP}  # it doesn't count against independence in the report
