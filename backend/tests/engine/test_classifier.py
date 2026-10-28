"""COD-6: spoken questions without Ask (the voice classifier), and the plan the analyzer keeps seeing (PLAN §9.7)."""

import asyncio
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pytest
from pydantic import BaseModel

from crucible.contracts.coding import Analysis, ProblemSpec
from crucible.contracts.events import InterventionText, TimelineKind, TranscriptTurn, TurnLabel
from crucible.engine.analyzer import build_messages
from crucible.engine.classifier import CONTEXT_TURNS, is_question_for_interviewer
from crucible.engine.context import RubricContext
from crucible.engine.ids import new_id
from crucible.engine.live import LiveEngine
from tests.factories import FakeModel, analysis, problem_json, runtime

CONTEXT = RubricContext.from_problem(ProblemSpec.model_validate(problem_json()))


class Voices:
    """A model that labels spoken turns from a script and answers questions; it records every call."""

    def __init__(self, labels: Callable[[str], str] | Exception) -> None:
        self.labels = labels
        self.calls: list[tuple[str, Sequence[Mapping[str, Any]]]] = []

    async def complete_json[T: BaseModel](
        self,
        role: str,
        messages: Sequence[Mapping[str, Any]],
        schema: type[T],
        *,
        session_id: str | None = None,
    ) -> T:
        self.calls.append((role, messages))
        if schema is TurnLabel:
            if isinstance(self.labels, Exception):
                raise self.labels
            turn = json.loads(messages[-1]["content"])["latest_turn"]
            return schema.model_validate({"label": self.labels(turn)})
        if schema is InterventionText:
            return schema.model_validate({"text": "It can be empty. What would you return then?"})
        return schema.model_validate(analysis(proposal=False))


def question_if_it_has_a_question_mark(turn: str) -> str:
    return "question_to_interviewer" if turn.endswith("?") else "thinking_aloud"


# --- the classifier call -------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_classifier_sees_the_turn_and_a_little_context() -> None:
    model = Voices(question_if_it_has_a_question_mark)
    earlier = ["one", "two", "three", "four", "five"]
    assert await is_question_for_interviewer(model, "can the list be empty?", earlier) is True
    assert await is_question_for_interviewer(model, "so I keep a running count", earlier) is False
    role, messages = model.calls[0]
    sent = json.loads(messages[-1]["content"])
    assert role == "classifier" and sent["latest_turn"] == "can the list be empty?"
    assert sent["earlier_turns"] == earlier[-CONTEXT_TURNS:]


@pytest.mark.asyncio
async def test_a_failed_classification_is_none_not_a_guess() -> None:
    assert await is_question_for_interviewer(Voices(RuntimeError("down")), "hello?", []) is None


# --- the engine: a spoken question gets answered ----------------------------------------------------------------------


def engine_with(model: Voices) -> tuple[Any, LiveEngine]:
    rt = runtime(model)  # type: ignore[arg-type]
    engine = LiveEngine(rt, CONTEXT, model)  # type: ignore[arg-type]
    rt._engine = engine  # what rt.attach() does, minus the background loops: tests tick by hand
    return rt, engine


async def say(rt: Any, text: str) -> TranscriptTurn:
    now = rt.now_ms()
    turn = TranscriptTurn(
        turn_id=new_id(), speaker="candidate", text=text, start_ms=now, end_ms=now, final=True, source="voice"
    )
    await rt.record(TimelineKind.TRANSCRIPT, turn)
    return turn


async def settle(engine: LiveEngine) -> None:
    for _ in range(50):
        if not engine._classifying:
            return
        await asyncio.sleep(0.01)


def answers(rt: Any) -> list[str]:
    return [
        e.payload["text"]
        for e in rt.timeline.tail([TimelineKind.INTERVENTION])
        if e.payload["trigger"] == "asked"
    ]


@pytest.mark.asyncio
async def test_a_spoken_question_without_ask_gets_answered() -> None:
    rt, engine = engine_with(Voices(question_if_it_has_a_question_mark))
    await say(rt, "can the readings list be empty?")
    await settle(engine)
    await engine.tick()
    assert answers(rt) == ["It can be empty. What would you return then?"]


@pytest.mark.asyncio
async def test_thinking_aloud_gets_no_answer() -> None:
    rt, engine = engine_with(Voices(question_if_it_has_a_question_mark))
    await say(rt, "so I walk the list and keep the best so far")
    await settle(engine)
    await engine.tick()
    assert answers(rt) == [] and engine.policy.asks == 0


@pytest.mark.asyncio
async def test_a_turn_held_on_ask_is_answered_once() -> None:
    rt, engine = engine_with(Voices(question_if_it_has_a_question_mark))
    turn = await say(rt, "is this right?")
    rt.asked(turn.text, turn.turn_id)  # the voice bridge, when Ask was held
    await settle(engine)
    assert engine.policy.asks == 1
    await engine.tick()
    assert len(answers(rt)) == 1


@pytest.mark.asyncio
async def test_a_classifier_failure_is_thinking_aloud_with_a_note() -> None:
    rt, engine = engine_with(Voices(RuntimeError("down")))
    await say(rt, "can it be empty?")
    await settle(engine)
    assert engine.policy.asks == 0
    notes = [e.payload["message"] for e in rt.timeline.tail([TimelineKind.SYSTEM])]
    assert any("voice classifier" in n for n in notes)


@pytest.mark.asyncio
async def test_typed_chat_never_goes_to_the_classifier() -> None:
    model = Voices(question_if_it_has_a_question_mark)
    rt, engine = engine_with(model)
    now = rt.now_ms()
    turn = TranscriptTurn(
        turn_id=new_id(),
        speaker="candidate",
        text="I'll loop once.",
        start_ms=now,
        end_ms=now,
        final=True,
        source="text",
    )
    await rt.record(TimelineKind.TRANSCRIPT, turn)
    await settle(engine)
    assert [role for role, _ in model.calls] == []


@pytest.mark.asyncio
async def test_stopping_the_engine_cancels_pending_classifications() -> None:
    gate = asyncio.Event()

    class Slow(Voices):
        async def complete_json(
            self, role: str, messages: Any, schema: Any, *, session_id: str | None = None
        ) -> Any:
            await gate.wait()
            return await super().complete_json(role, messages, schema, session_id=session_id)

    rt, engine = engine_with(Slow(question_if_it_has_a_question_mark))
    await say(rt, "can it be empty?")
    assert engine._classifying
    await engine.stop()
    assert not engine._classifying


# --- the plan the analyzer keeps seeing ----------------------------------------------------------------------------


def test_the_analyzer_is_shown_the_plan_stated_earlier() -> None:
    from tests.engine.test_analyzer import view

    prompt = build_messages(CONTEXT, view(plan="Walk the list once with a running count."))[-1]["content"]
    assert "## The plan they stated earlier\nWalk the list once with a running count." in prompt
    assert "The plan they stated earlier" not in build_messages(CONTEXT, view())[-1]["content"]


@pytest.mark.asyncio
async def test_the_analyzer_remembers_the_latest_stated_plan() -> None:
    model = FakeModel(analysis(proposal=False), analysis(proposal=False) | {"stated_plan": None})
    rt = runtime(model)
    await rt.attach(CONTEXT)
    analyzer = rt._engine.analyzer  # type: ignore[union-attr]
    try:
        await analyzer.run("pause")
        await analyzer.run("pause")
    finally:
        await rt.detach()
    assert analyzer.plan == Analysis.model_validate(analysis(proposal=False)).stated_plan
