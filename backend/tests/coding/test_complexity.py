"""COD-5: grading the wrap-up complexity answer (PLAN §10.5). The model writes down the stated bounds; code
decides whether they match an acceptable approach."""

import itertools
import json
from pathlib import Path

import pytest

from crucible.coding.complexity import (
    canonical,
    complexity_answer,
    complexity_question,
    grade_complexity_answer,
    matches_acceptable,
    same_bound,
)
from crucible.coding.problems import ProblemBank
from crucible.coding.session import CodingMode
from crucible.contracts.coding import Approach, ComplexityClaim, ProblemSpec
from crucible.contracts.events import (
    Intervention,
    InterventionLevel,
    InterventionTrigger,
    TimelineEvent,
    TimelineKind,
    TranscriptTurn,
)
from crucible.engine.ids import new_id
from tests.factories import FakeModel, problem_json, runtime, write_quiet_streak

SPEC = ProblemSpec.model_validate(problem_json())  # quiet-streak: O(n)/O(1) acceptable, O(n^2)/O(1) not
GROUPS = [  # ingredient-groups: two acceptable approaches with different bounds, one not
    Approach(name="sorted key", time="O(n * m log m)", space="O(n * m)", acceptable=True),
    Approach(name="count tuple key", time="O(n * m)", space="O(n)", acceptable=True),
    Approach(name="compare every pair", time="O(n^2 * m log m)", space="O(n)", acceptable=False),
]


def claim(time: str | None, space: str | None) -> ComplexityClaim:
    return ComplexityClaim(time=time, space=space)


# --- bounds, up to notation ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("O(n * m log m)", "O(nm log(m))"),
        ("O(n * m log m)", "O(m log m · n)"),
        ("O(n^2)", "O(n²)"),
        ("O(n + r)", "O(r + n)"),
        ("O(n)", "O(2n + 1)"),
        ("O(n log n)", "O(n + n log n)"),
        ("O(1)", "constant"),
        ("O(n)", "linear time"),
        ("O(n)", "Θ(n)"),
    ],
)
def test_the_same_bound_in_other_notation(a: str, b: str) -> None:
    assert same_bound(a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [("O(n)", "O(n log n)"), ("O(n)", "O(n^2)"), ("O(n * m)", "O(n * m log m)"), ("O(n + r)", "O(n * r)")],
)
def test_different_bounds_differ(a: str, b: str) -> None:
    assert not same_bound(a, b)


def test_an_unreadable_bound_is_compared_as_text() -> None:
    assert canonical("O(n, m)") is None and canonical("O()") is None
    assert same_bound("O(n, m)", "O(n,m)") and not same_bound("O(n, m)", "O(n)")


# --- the decision -----------------------------------------------------------------------------------------------


def test_time_and_space_of_an_acceptable_approach_match() -> None:
    assert matches_acceptable(claim("O(n)", "O(1)"), SPEC.rubric.approaches)
    assert matches_acceptable(claim("O(n * m)", "O(n)"), GROUPS)


def test_a_missing_space_bound_isnt_held_against_them() -> None:
    assert matches_acceptable(claim("O(n)", None), SPEC.rubric.approaches)


def test_a_wrong_or_missing_time_bound_doesnt_match() -> None:
    assert not matches_acceptable(claim("O(n log n)", "O(1)"), SPEC.rubric.approaches)
    assert not matches_acceptable(claim(None, "O(1)"), SPEC.rubric.approaches)


def test_the_bounds_of_an_unacceptable_approach_dont_match() -> None:
    assert not matches_acceptable(claim("O(n^2)", "O(1)"), SPEC.rubric.approaches)


def test_time_and_space_must_come_from_the_same_approach() -> None:
    assert not matches_acceptable(claim("O(n * m)", "O(n * m)"), GROUPS)


def test_a_wrong_space_bound_doesnt_match() -> None:
    assert not matches_acceptable(claim("O(n)", "O(n^2)"), SPEC.rubric.approaches)


def test_leaving_out_an_added_term_still_matches() -> None:
    sampler = [Approach(name="sliding window", time="O(n + r)", space="O(r)", acceptable=True)]
    assert matches_acceptable(claim("O(n)", "O(r)"), sampler)
    assert not matches_acceptable(claim("O(n * r)", "O(r)"), sampler)


# --- finding the answer on the timeline --------------------------------------------------------------------------


def asked(t: int, text: str) -> TimelineEvent:
    return event(
        TimelineKind.INTERVENTION,
        t,
        Intervention(
            id=new_id(),
            t=t,
            trigger=InterventionTrigger.PHASE,
            level=InterventionLevel.QUESTION,
            text=text,
            step_id=None,
            speak=True,
            suppressed=False,
        ).model_dump(mode="json"),
    )


def said(t: int, text: str, start_ms: int | None = None, speaker: str = "candidate") -> TimelineEvent:
    turn = TranscriptTurn(
        turn_id=new_id(),
        speaker=speaker,  # type: ignore[arg-type]
        text=text,
        start_ms=t if start_ms is None else start_ms,
        end_ms=t,
        final=True,
        source="voice",
    )
    return event(TimelineKind.TRANSCRIPT, t, turn.model_dump(mode="json"))


SEQ = itertools.count(1)


def event(kind: TimelineKind, t: int, payload: dict) -> TimelineEvent:
    return TimelineEvent(seq=next(SEQ), t=t, kind=kind, payload=payload)


def test_the_complexity_question_is_found_by_its_wording() -> None:
    assert complexity_question(SPEC.rubric.wrap_up_questions) == 0
    assert complexity_question(["How would you stream it?", "What's the time complexity?"]) == 1
    assert complexity_question(["How would you stream it?"]) is None


def test_the_answer_is_what_they_said_between_the_two_questions() -> None:
    events = [
        said(500, "I'm done."),
        asked(1_000, "What are the time and space complexity?"),
        said(1_000, "What are the time and space complexity?", speaker="interviewer"),
        said(3_000, "Linear time,"),
        asked(4_000, "How would you stream it?"),
        said(5_000, "and constant space.", start_ms=3_500),  # started before the next question
        said(9_000, "I'd keep the last reading."),
    ]
    assert complexity_answer(events, 0) == "Linear time, and constant space."


def test_a_typed_answer_recorded_in_the_same_millisecond_as_the_next_question_counts() -> None:
    events = [
        asked(1_000, "What are the time and space complexity?"),
        said(3_000, "O(n) time, O(1) space."),
        asked(3_000, "How would you stream it?"),  # the answer triggered it: same t, later seq
        said(5_000, "Keep the last reading."),
    ]
    assert complexity_answer(events, 0) == "O(n) time, O(1) space."


def test_no_question_or_no_answer_is_nothing_to_grade() -> None:
    assert complexity_answer([said(500, "O(n)")], 0) is None
    assert complexity_answer([asked(1_000, "What are the time and space complexity?")], 0) is None


# --- the model call -----------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_model_writes_down_the_bounds_and_code_grades_them() -> None:
    model = FakeModel({"time": "O(n)", "space": "O(1)"}, {"time": "O(n^2)", "space": "O(1)"})
    assert await grade_complexity_answer(model, SPEC, "linear and constant") is True
    assert await grade_complexity_answer(model, SPEC, "n squared") is False
    sent = json.loads(model.calls[0][-1]["content"])
    assert sent["answer"] == "linear and constant"
    assert sent["rubric_approaches"][0] == {
        "name": SPEC.rubric.approaches[0].name,
        "time": "O(n)",
        "space": "O(1)",
    }
    assert "acceptable" not in json.dumps(sent)  # the model writes down what was said; it doesn't grade


@pytest.mark.asyncio
async def test_a_failed_model_call_leaves_it_ungraded() -> None:
    assert await grade_complexity_answer(FakeModel(RuntimeError("down")), SPEC, "O(n)") is None


# --- the report extras ----------------------------------------------------------------------------------------------


async def graded(
    tmp_path: Path, model: FakeModel | None, answer: str | None
) -> tuple[bool | None, list[str]]:
    write_quiet_streak(tmp_path)
    rt = runtime(model)
    questions = SPEC.rubric.wrap_up_questions
    rt.timeline.append(TimelineKind.INTERVENTION, asked(1_000, questions[0]).payload, t=1_000)
    if answer is not None:
        rt.timeline.append(TimelineKind.TRANSCRIPT, said(2_000, answer).payload, t=2_000)
    rt.timeline.append(TimelineKind.INTERVENTION, asked(3_000, questions[1]).payload, t=3_000)
    extra = await CodingMode(ProblemBank.load(tmp_path))().report_extra(rt)
    notes = [e.payload["message"] for e in await rt.timeline.read({TimelineKind.SYSTEM})]
    return extra.complexity_answer_ok, notes


@pytest.mark.asyncio
async def test_the_report_extras_grade_the_complexity_answer(tmp_path: Path) -> None:
    model = FakeModel({"time": "O(n)", "space": "O(1)"})
    assert await graded(tmp_path, model, "O of n time, O of 1 space") == (True, [])


@pytest.mark.asyncio
async def test_an_unanswered_question_isnt_graded(tmp_path: Path) -> None:
    model = FakeModel({"time": "O(n)", "space": "O(1)"})
    assert await graded(tmp_path, model, None) == (None, [])
    assert model.calls == []


@pytest.mark.asyncio
async def test_a_grading_failure_is_ungraded_with_a_note(tmp_path: Path) -> None:
    ok, notes = await graded(tmp_path, FakeModel(RuntimeError("down")), "O(n)")
    assert ok is None and any("complexity answer" in n for n in notes)


@pytest.mark.asyncio
async def test_without_a_model_nothing_is_graded(tmp_path: Path) -> None:
    assert await graded(tmp_path, None, "O(n)") == (None, [])
