"""Grill scoring is code (PLAN §11.5): root cause required, invented indexes ignored, SAM bonus capped."""

from crucible.contracts.defense import GrillEval
from crucible.defense.grill import keyword_eval, looks_like_code, score_answer
from tests.defense.fixtures import GOOD_ANSWER, WEAK_ANSWER


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
