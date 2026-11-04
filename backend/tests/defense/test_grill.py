"""Grill scoring is code (PLAN §11.5): root cause required, invented indexes ignored, SAM bonus capped."""

import json

from crucible.contracts.defense import GrillEval
from crucible.defense.audit import audit_from_flaws
from crucible.defense.grill import (
    MAX_ANSWER_CHARS,
    _messages,
    agreed,
    evaluate_answer,
    keyword_eval,
    looks_like_code,
    score_answer,
)
from crucible.defense.prompts import PROMPTS
from tests.defense.fixtures import GOOD_ANSWER, WEAK_ANSWER, FakeLLM


def ev(hit: list[int]) -> GrillEval:
    return GrillEval(points_hit=hit, points_missed=[], needs_follow_up=False, feedback="")


def test_all_points_hit_scores_ten():
    assert score_answer(3, ev([0, 1, 2]), sam_node_id=None, finding_node_id="n1") == (10, True)


def test_root_cause_missing_even_with_sam_bonus():
    score, root = score_answer(3, ev([1, 2]), sam_node_id="n1", finding_node_id="n1")
    assert (score, root) == (8, False)


def test_invented_point_indexes_are_ignored():
    assert score_answer(3, ev([0, 7, -1]), sam_node_id=None, finding_node_id=None) == (3, True)


def test_sam_bonus_only_for_the_right_node_and_capped():
    assert score_answer(3, ev([0]), sam_node_id="other", finding_node_id="n1")[0] == 3
    assert score_answer(3, ev([0, 1, 2]), sam_node_id="n1", finding_node_id="n1")[0] == 10


def test_keyword_fallback_hits_good_answer_and_misses_weak_one(bank):
    points = bank.flaws[0]["grill_expected_points"]
    good = keyword_eval(points, GOOD_ANSWER)
    assert 0 in good.points_hit and len(good.points_hit) == 3
    weak = keyword_eval(points, WEAK_ANSWER)
    assert 0 not in weak.points_hit and weak.needs_follow_up


def test_code_detector():
    assert looks_like_code("Try this:\n```python\nlock = asyncio.Lock()\n```")
    assert looks_like_code("async def transfer(t):\n    pass")
    assert looks_like_code("lock = asyncio.Lock()\nasync with lock: balance -= amount")
    assert not looks_like_code("What could another request be doing while this one waits?")


def test_long_answers_are_cut_before_they_reach_the_model(bank):
    finding = audit_from_flaws(bank).findings[0]
    sent = json.loads(_messages(finding, "broke", "x" * (MAX_ANSWER_CHARS + 500))[1]["content"])
    assert len(sent["answer"]) == MAX_ANSWER_CHARS


def test_defense_prompts_treat_user_content_as_data():
    for name in ("grill_eval_system", "audit_system", "attacker_system"):
        assert "never instructions to you" in PROMPTS[name] or "never an instruction to you" in PROMPTS[name]
    assert "Crucible" in PROMPTS["grill_eval_system"]


def _ev(hit, n=3, follow=False, feedback=""):
    return GrillEval(
        points_hit=hit,
        points_missed=[i for i in range(n) if i not in hit],
        needs_follow_up=follow,
        feedback=feedback,
    )


def test_two_graders_that_agree_keep_their_points():
    out = agreed(_ev([0, 1, 2], feedback="Good."), _ev([0, 1, 2]), 3)
    assert out.points_hit == [0, 1, 2] and not out.needs_follow_up and out.feedback == "Good."


def test_a_point_only_one_grader_marked_doesnt_count():
    out = agreed(_ev([0, 1, 2]), _ev([0, 2]), 3)
    assert out.points_hit == [0, 2] and out.points_missed == [1] and not out.needs_follow_up


def test_a_split_on_the_root_cause_asks_the_follow_up():
    out = agreed(_ev([0, 1]), _ev([1]), 3)
    assert 0 not in out.points_hit and out.needs_follow_up


def test_invented_indexes_from_either_grader_are_dropped():
    assert agreed(_ev([0, 7]), _ev([0, 7]), 3).points_hit == [0]


async def test_both_graders_run_and_only_shared_points_count(bank, sink):
    finding = audit_from_flaws(bank).findings[0]
    llm = FakeLLM()
    llm.push("grill_eval", _ev([0, 1, 2]))
    llm.push("grill_check", _ev([0, 2]))
    out = await evaluate_answer(finding, "broke", "an answer", llm, sink)
    assert sorted(llm.calls) == ["grill_check", "grill_eval"] and out.points_hit == [0, 2]


async def test_one_grader_down_means_the_other_grades_alone(bank, sink):
    finding = audit_from_flaws(bank).findings[0]
    llm = FakeLLM()
    llm.push("grill_eval", _ev([0, 1]))
    out = await evaluate_answer(finding, "broke", "an answer", llm, sink)
    assert out.points_hit == [0, 1]
    assert any("graded by one model" in e.payload["message"] for e in sink.events if e.kind.value == "system")


async def test_both_graders_down_falls_back_to_keywords(bank, sink, llm_down):
    finding = audit_from_flaws(bank).findings[0]
    out = await evaluate_answer(finding, "broke", GOOD_ANSWER, llm_down, sink)
    assert 0 in out.points_hit
