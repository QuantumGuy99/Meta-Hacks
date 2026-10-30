"""Tests for engine/live.py: the policy fed from the timeline and the hub, and its delivery (PLAN §9.5, §9.6)."""

import asyncio
import json
from typing import Any

import pytest

from crucible.contracts.coding import ProblemSpec
from crucible.contracts.common import Phase
from crucible.contracts.events import CodeSnapshot, EditorChange, EditorEvent, TimelineKind
from crucible.contracts.ws import ChatSend, EditorEvents, EditorSnapshot, HintRequest
from crucible.engine.context import RubricContext
from crucible.engine.hub import Connection, SessionRuntime
from crucible.engine.interviewer import deliver
from crucible.engine.live import LiveEngine
from crucible.engine.policy import IDLE_AFTER_MS, Decision
from crucible.engine.prompts import CANNED
from tests.factories import FakeModel, analysis, problem_json, runtime

CONTEXT = RubricContext.from_problem(ProblemSpec.model_validate(problem_json()))
STARTER = "def longest_quiet_streak(readings: list[int], threshold: int) -> int:\n    pass\n"


class Clock:
    def __init__(self) -> None:
        self.s = 0.0

    def __call__(self) -> float:
        return self.s


class Socket:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_text(self, data: str) -> None:
        self.sent.append(json.loads(data))


def live(clock: Clock, **config: Any) -> tuple[SessionRuntime, LiveEngine, Connection, Socket]:
    """A runtime with an engine whose tasks aren't started, so each test ticks it by hand."""
    rt = runtime(monotonic=clock, **config)
    engine = LiveEngine(rt, CONTEXT, FakeModel(analysis()))
    rt._engine = engine  # what rt.attach() does, minus the background tasks
    socket = Socket()
    return rt, engine, rt.add(socket), socket


def interventions(rt: SessionRuntime) -> list[dict[str, Any]]:
    return [e.payload for e in rt.timeline.tail([TimelineKind.INTERVENTION])]


@pytest.mark.asyncio
async def test_a_hint_request_from_the_browser_gets_the_next_rubric_hint() -> None:
    rt, engine, connection, socket = live(Clock())
    await rt.handle(connection, HintRequest(type="hint.request"))
    await engine.tick()
    [hint] = interventions(rt)
    assert (hint["trigger"], hint["level"], hint["step_id"]) == ("hint_requested", "nudge", "s1")
    assert hint["text"] == CONTEXT.steps[0].hints[0] and hint["speak"]
    assert [m["type"] for m in socket.sent] == ["interviewer.message"]
    assert engine.policy.hints_by_level == {"nudge": 1}


@pytest.mark.asyncio
async def test_a_hint_request_without_a_live_interviewer_is_refused() -> None:
    rt, socket = runtime(), Socket()
    await rt.handle(rt.add(socket), HintRequest(type="hint.request"))
    assert (socket.sent[0]["type"], socket.sent[0]["code"]) == ("error", "unsupported")


@pytest.mark.asyncio
async def test_a_question_in_chat_gets_an_answer_and_thinking_aloud_does_not() -> None:
    rt, engine, connection, _ = live(Clock())
    await rt.handle(connection, ChatSend(type="chat.send", text="I'll loop over the readings."))
    await engine.tick()
    assert interventions(rt) == []
    await rt.handle(connection, ChatSend(type="chat.send", text="Can the list be empty?"))
    await engine.tick()
    [answer] = interventions(rt)
    assert (answer["trigger"], answer["text"]) == ("asked", CANNED["asked"])


@pytest.mark.asyncio
async def test_questions_asked_before_the_reply_are_answered_together() -> None:
    rt, engine, _, _ = live(Clock())
    rt.asked("Can the readings list be empty?")  # a spoken question, split into two turns
    rt.asked("And does a reading equal to the threshold count?")
    await engine.tick()
    [answer] = interventions(rt)
    assert answer["trigger"] == "asked"
    prompt = engine._model.calls[-1][-1]["content"]  # type: ignore[attr-defined]
    assert prompt.endswith("Can the readings list be empty? And does a reading equal to the threshold count?")


@pytest.mark.asyncio
async def test_passive_mode_still_answers_questions() -> None:
    rt, engine, connection, socket = live(Clock(), feedback="passive")
    await rt.handle(connection, ChatSend(type="chat.send", text="What should an empty list return?"))
    await engine.tick()
    [answer] = interventions(rt)
    assert not answer["suppressed"] and "interviewer.message" in [m["type"] for m in socket.sent]


@pytest.mark.asyncio
async def test_a_pasted_block_gets_one_text_only_note_once_typing_pauses() -> None:
    clock = Clock()
    rt, engine, connection, _ = live(clock)
    block = EditorChange(range_offset=0, range_length=0, text="for r in readings:\n    total += r\n")
    clock.s = 10
    await rt.handle(
        connection,
        EditorEvents(
            type="editor.events", events=[EditorEvent(t=10_000, version=2, kind="paste", changes=[block])]
        ),
    )
    await engine.tick()
    assert interventions(rt) == []  # still inside the quiet window after the edit
    clock.s = 13
    await engine.tick()
    [note] = interventions(rt)
    assert (note["trigger"], note["text"], note["speak"]) == ("paste", CANNED["paste"], False)


@pytest.mark.asyncio
async def test_time_warnings_are_text_only_and_say_the_minutes_left() -> None:
    clock = Clock()
    rt, engine, _, _ = live(clock)
    clock.s = 600  # half of the 20-minute limit
    await engine.tick()
    [warning] = interventions(rt)
    assert warning["trigger"] == "time_warning" and not warning["speak"]
    assert warning["text"] == CANNED["time_warning"].format(minutes=10)


@pytest.mark.asyncio
async def test_the_idle_clock_starts_when_coding_starts() -> None:
    clock = Clock()
    rt, engine, _, _ = live(clock)
    clock.s = 100
    rt.session.phase = Phase.CODING
    await engine.tick()
    clock.s = 100 + IDLE_AFTER_MS / 1000 - 1
    await engine.tick()
    assert interventions(rt) == []
    clock.s = 100 + IDLE_AFTER_MS / 1000
    await engine.tick()
    assert [i["trigger"] for i in interventions(rt)] == ["idle"]


@pytest.mark.asyncio
async def test_lines_are_counted_from_the_starter_code_the_editor_loaded() -> None:
    rt, engine, connection, _ = live(Clock())
    written = STARTER.replace("    pass\n", "    best = 0\n    cur = 0\n    return best\n")
    for version, code in enumerate([STARTER, written]):
        snapshot = CodeSnapshot(t=0, file="solution.py", version=version, code=code)
        await rt.handle(connection, EditorSnapshot(type="editor.snapshot", snapshot=snapshot))
    assert engine._facts().lines_written == 3


@pytest.mark.asyncio
async def test_a_failed_delivery_leaves_a_note_and_the_interviewer_keeps_going(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed, delivered = asyncio.Event(), asyncio.Event()

    async def flaky(rt: SessionRuntime, decision: Decision, context: RubricContext) -> object:
        if not failed.is_set():
            failed.set()
            raise RuntimeError("socket gone")
        intervention = await deliver(rt, decision, context)
        delivered.set()
        return intervention

    monkeypatch.setattr("crucible.engine.live.deliver", flaky)
    rt, engine, _, _ = live(Clock())
    engine.start()  # the real loop this time: its task boundary is what's under test
    try:
        async with asyncio.timeout(3):
            engine.request_hint(None)
            await failed.wait()
            engine.request_hint(None)
            await delivered.wait()
    finally:
        await engine.stop()
    assert "couldn't deliver" in rt.timeline.tail([TimelineKind.SYSTEM])[0].payload["message"]
    assert interventions(rt)[0]["trigger"] == "hint_requested"
