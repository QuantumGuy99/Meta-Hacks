"""The interviewer's side of the conversation (PLAN §9.5): replies to what the candidate says, questions that check
they understand what they wrote, and check-ins. Talk isn't help: its own clocks, no help cap, no ladder."""

import asyncio
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pytest
from pydantic import BaseModel

from crucible.contracts.coding import Analysis, ProblemSpec
from crucible.contracts.common import Phase
from crucible.contracts.events import (
    InterventionLevel,
    InterventionText,
    InterventionTrigger,
    TimelineKind,
    TranscriptTurn,
    TurnLabel,
)
from crucible.engine.context import RubricContext
from crucible.engine.ids import new_id
from crucible.engine.live import LiveEngine
from crucible.engine.policy import (
    COOLDOWN_MS,
    IDLE_AFTER_MS,
    PROBE_AFTER_MS,
    PROBE_MAX,
    REPLY_AFTER_MS,
    REPLY_EVERY_MS,
    REPLY_MAX,
    REPLY_STALE_MS,
    TALK_GAP_MS,
    PolicyState,
    decide,
)
from tests.engine.test_policy import CLEAN, NOW, facts, seen, what
from tests.engine.test_voice import Clock
from tests.factories import analysis, problem_json, runtime

Trigger, Level = InterventionTrigger, InterventionLevel
PLAN = "So I'll walk the readings once and keep a running count of quiet ones."
QUIET = NOW - REPLY_AFTER_MS  # the interviewer's last line, long enough ago for a reply


def talking(last_message_ms: int = QUIET, **fields: Any) -> PolicyState:
    """A clean analysis (nothing to help with) and an interviewer that has been quiet for a while."""
    return seen(CLEAN, CLEAN, state=PolicyState(last_message_ms=last_message_ms, **fields))


def finished(*done: str) -> dict[str, Any]:
    """An analysis with these steps done and nothing to help with."""
    statuses = {"s1": "done", "s2": "in_progress"} | {step: "done" for step in done}
    return analysis(statuses["s1"], statuses["s2"], proposal=False)


# --- REPLY -----------------------------------------------------------------------------------------------------------


def test_a_statement_gets_a_reply_with_what_was_said() -> None:
    state = talking()
    state.observe_statement(PLAN, NOW - 1_000)
    decision = decide(state, facts())
    assert what(decision) == (Trigger.REPLY, Level.INFO, None)
    assert decision is not None and decision.said == PLAN and decision.draft is None


@pytest.mark.parametrize(
    ("said", "said_ms", "last_line_ms", "phase"),
    [
        ("okay let me think", NOW - 1_000, QUIET, Phase.CODING),  # too short to answer
        (PLAN, NOW - REPLY_STALE_MS - 1, QUIET, Phase.CODING),  # said too long ago
        (PLAN, NOW - 1_000, NOW - REPLY_AFTER_MS + 1, Phase.CODING),  # the interviewer just spoke
        (PLAN, NOW - 1_000, QUIET, Phase.WRAP_UP),  # the wrap-up's questions are scripted
    ],
)
def test_no_reply(said: str, said_ms: int, last_line_ms: int, phase: Phase) -> None:
    state = talking()
    state.last_message_ms = last_line_ms
    state.observe_statement(said, said_ms)
    assert decide(state, facts(phase=phase)) is None


def test_no_reply_in_passive_mode() -> None:
    state = talking()
    state.observe_statement(PLAN, NOW - 1_000)
    assert decide(state, facts(passive=True)) is None


def test_replies_are_spaced_and_capped() -> None:
    state = talking(last_reply_ms=NOW - REPLY_EVERY_MS + 1)
    state.observe_statement(PLAN, NOW - 1_000)
    assert decide(state, facts()) is None
    state = talking(replies=REPLY_MAX)
    state.observe_statement(PLAN, NOW - 1_000)
    assert decide(state, facts()) is None


def test_a_reply_waits_for_the_candidate_to_stop_typing() -> None:
    state = talking()
    state.observe_statement(PLAN, NOW - 1_000)
    assert decide(state, facts(last_edit_ms=NOW - 500)) is None
    assert what(decide(state, facts(NOW + 2_500, last_edit_ms=NOW - 500))) == (
        Trigger.REPLY,
        Level.INFO,
        None,
    )


def test_a_reply_to_a_finished_turn_doesnt_wait_out_the_quiet_window() -> None:
    state = talking()
    state.observe_statement(PLAN, NOW)  # the final transcript just came in
    finished_turn = facts(last_partial_ms=NOW - 300, last_speech_ms=NOW)  # the turn's own partials
    assert what(decide(state, finished_turn)) == (Trigger.REPLY, Level.INFO, None)


def test_a_reply_waits_if_they_start_talking_again() -> None:
    state = talking()
    state.observe_statement(PLAN, NOW - 1_000)
    assert decide(state, facts(last_partial_ms=NOW - 200)) is None  # a new turn under way


def test_talk_counts_from_when_the_problem_was_presented() -> None:
    state = seen(CLEAN, CLEAN, state=PolicyState(attached_ms=NOW - 5_000))
    state.observe_statement(PLAN, NOW - 1_000)
    assert decide(state, facts()) is None


# --- PROBE -----------------------------------------------------------------------------------------------------------

LONG_QUIET = NOW - PROBE_AFTER_MS


def test_a_step_just_done_gets_a_probe_the_model_words() -> None:
    state = talking(last_message_ms=LONG_QUIET)
    seen(finished("s2"), state=state)
    decision = decide(state, facts())
    assert what(decision) == (Trigger.PROBE, Level.QUESTION, "s1")  # s1 and s2 done; one probe for both
    assert decision is not None and decision.draft is None
    assert state.probed == {"s1", "s2"}


@pytest.mark.parametrize(
    ("phase", "last_line_ms"),
    [
        (Phase.CLARIFY, LONG_QUIET),  # no code to ask about yet
        (Phase.CODING, LONG_QUIET + 1),  # too soon after the last line
    ],
)
def test_no_probe(phase: Phase, last_line_ms: int) -> None:
    state = talking(last_message_ms=last_line_ms)
    seen(finished("s2"), state=state)
    assert decide(state, facts(phase=phase)) is None


def test_no_probe_in_passive_mode() -> None:
    state = talking(last_message_ms=LONG_QUIET)
    seen(finished("s2"), state=state)
    assert decide(state, facts(passive=True)) is None


def test_each_step_is_probed_once_and_probes_are_capped() -> None:
    state = talking(last_message_ms=LONG_QUIET)
    assert decide(state, facts()) is not None  # s1 done
    seen(finished(), state=state)
    assert decide(state, facts(NOW + PROBE_AFTER_MS)) is None  # nothing new got done
    seen(finished("s2"), state=state)
    assert what(decide(state, facts(NOW + PROBE_AFTER_MS))) == (Trigger.PROBE, Level.QUESTION, "s2")
    state = talking(last_message_ms=LONG_QUIET, probes=PROBE_MAX)
    assert decide(state, facts()) is None


def test_no_probe_while_a_bug_is_suspected() -> None:
    state = talking(last_message_ms=LONG_QUIET)
    issue = {"kind": "bug", "line": 4, "mistake_id": None, "description": "off by one", "confidence": 0.9}
    seen(finished("s2") | {"issues": [issue]}, state=state)
    assert decide(state, facts()) is None


def test_help_comes_before_a_probe() -> None:
    state = seen(analysis(), analysis(), state=PolicyState(last_message_ms=LONG_QUIET))
    assert what(decide(state, facts()))[0] == Trigger.MISSED_STEP  # type: ignore[index]


def test_a_check_in_waits_after_the_interviewers_own_question() -> None:
    state = talking(last_message_ms=NOW - 16_000)  # e.g. a probe 16 s ago, still unanswered
    quiet = facts(last_edit_ms=NOW - IDLE_AFTER_MS, last_speech_ms=NOW - IDLE_AFTER_MS)
    assert decide(state, quiet) is None
    later = facts(
        NOW + IDLE_AFTER_MS - 16_000, last_edit_ms=NOW - IDLE_AFTER_MS, last_speech_ms=NOW - IDLE_AFTER_MS
    )
    assert what(decide(state, later))[0] == Trigger.IDLE  # type: ignore[index]


# --- talk and help share the floor, not the budget -----------------------------------------------------------------


def test_nothing_unsolicited_within_15_s_of_any_line() -> None:
    state = seen(analysis(), analysis(), state=PolicyState(last_message_ms=NOW - TALK_GAP_MS + 1))
    assert decide(state, facts()) is None
    assert what(decide(state, facts(NOW + 1))) == (Trigger.MISSED_STEP, Level.QUESTION, "s1")


def test_talk_doesnt_use_the_help_cooldown_cap_or_ladder() -> None:
    state = talking()
    state.observe_statement(PLAN, NOW - 1_000)
    assert decide(state, facts()) is not None
    assert state.last_help_ms is None and not state.unsolicited_ms
    assert state.ladder == {} and state.hints_by_level == {}
    seen(analysis(), analysis(), state=state)  # help can follow 15 s later, not 45
    assert what(decide(state, facts(NOW + TALK_GAP_MS)))[0] == Trigger.MISSED_STEP  # type: ignore[index]
    assert TALK_GAP_MS < COOLDOWN_MS


# --- the live engine: the model writes replies and check-ins ---------------------------------------------------------

CONTEXT = RubricContext.from_problem(ProblemSpec.model_validate(problem_json()))
REPLY = "Why a running count rather than keeping every reading?"
CHECK_IN = "I see the loop is in place. Where are you headed next?"


class Talker:
    """Labels spoken turns from a script, writes replies and check-ins, and never proposes help."""

    def __init__(self, label: Callable[[str], str]) -> None:
        self.label = label
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
            turn = json.loads(messages[-1]["content"])["latest_turn"]
            return schema.model_validate({"label": self.label(turn)})
        if schema is InterventionText:
            checkin = messages[0]["content"].startswith("# interviewer_checkin")
            return schema.model_validate({"text": CHECK_IN if checkin else REPLY})
        return schema.model_validate(CLEAN)

    def roles(self) -> list[str]:
        return [role for role, _ in self.calls]


def engine(label: Callable[[str], str] = lambda _: "thinking_aloud") -> tuple[Any, LiveEngine, Talker, Clock]:
    clock, model = Clock(), Talker(label)
    rt = runtime(model, monotonic=clock)  # type: ignore[arg-type]
    live = LiveEngine(rt, CONTEXT, model)  # type: ignore[arg-type]
    rt._engine = live  # what rt.attach() does, minus the background loops: tests tick by hand
    clock.now += REPLY_AFTER_MS / 1000  # the problem was presented a while ago
    return rt, live, model, clock


async def say(rt: Any, text: str, source: str = "voice") -> None:
    now = rt.now_ms()
    turn = TranscriptTurn(
        turn_id=new_id(), speaker="candidate", text=text, start_ms=now, end_ms=now, final=True, source=source
    )  # type: ignore[arg-type]
    await rt.record(TimelineKind.TRANSCRIPT, turn)


async def settle(live: LiveEngine) -> None:
    for _ in range(50):
        if not live._classifying:
            return
        await asyncio.sleep(0.01)


def lines(rt: Any) -> list[tuple[str, str]]:
    return [(e.payload["trigger"], e.payload["text"]) for e in rt.timeline.tail([TimelineKind.INTERVENTION])]


@pytest.mark.asyncio
async def test_thinking_aloud_gets_the_models_reply() -> None:
    rt, live, model, _ = engine()
    await say(rt, PLAN)
    await settle(live)
    await live.tick()
    assert lines(rt) == [("reply", REPLY)]
    # The answer and the reply were written while the classifier decided; the reply was used.
    assert sorted(model.roles()) == ["classifier", "conversation", "interviewer"]
    sent = next(m for role, m in model.calls if role == "conversation")[-1]["content"]
    assert "## What they just said\n" + PLAN in sent


@pytest.mark.asyncio
async def test_a_typed_statement_gets_a_reply_and_a_typed_question_an_answer() -> None:
    rt, live, model, _ = engine()
    await say(rt, PLAN, source="text")
    await live.tick()
    assert lines(rt) == [("reply", REPLY)]
    assert model.roles() == ["conversation"]  # typed chat never goes to the classifier


@pytest.mark.asyncio
async def test_a_spoken_question_is_still_answered_not_replied_to() -> None:
    rt, live, model, _ = engine(label=lambda _: "question_to_interviewer")
    await say(rt, "Can the readings list be empty, or is it always at least one reading?")
    await settle(live)
    await live.tick()
    assert [trigger for trigger, _ in lines(rt)] == ["asked"]
    assert sorted(model.roles()) == ["classifier", "conversation", "interviewer"]  # the reply was discarded


@pytest.mark.asyncio
async def test_the_answer_written_ahead_is_the_one_sent() -> None:
    rt, live, model, _ = engine(label=lambda _: "question_to_interviewer")
    await say(rt, "Can the readings list be empty, or is it always at least one reading?")
    await settle(live)
    await live.tick()
    assert [trigger for trigger, _ in lines(rt)] == ["asked"]
    assert model.roles().count("interviewer") == 1  # written once, while the classifier ran


@pytest.mark.asyncio
async def test_a_check_in_is_written_by_the_model() -> None:
    rt, live, model, clock = engine()
    rt.session.phase = Phase.CODING
    await live.tick()  # the engine notices coding started
    clock.now += IDLE_AFTER_MS / 1000
    await live.tick()
    assert lines(rt) == [("idle", CHECK_IN)]
    assert model.roles()[-1] == "conversation"


def test_the_analysis_fixture_proposes_nothing() -> None:
    assert Analysis.model_validate(CLEAN).proposal is None
