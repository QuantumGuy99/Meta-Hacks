"""Starter code, signatures and case input for Java, C++ and C (coding/languages.py, PLAN §10.3)."""

import pytest

from crucible.coding import languages
from crucible.coding.problems import ProblemBank
from crucible.contracts.coding import FunctionSig, Param
from crucible.contracts.common import Language
from crucible.engine.context import RubricContext

BUDGET = FunctionSig(
    name="longest_within_budget",
    params=[Param(name="usage", type="list[int]"), Param(name="budget", type="int")],
    returns="int",
)
BOOKINGS = FunctionSig(
    name="merge_bookings", params=[Param(name="bookings", type="list[list[int]]")], returns="list[list[int]]"
)


def test_python_keeps_the_problems_own_starter() -> None:
    assert languages.starter(BUDGET, Language.PYTHON, "def f():\n    pass\n") == "def f():\n    pass\n"


def test_java_starter_is_a_solution_class_with_camel_case_names() -> None:
    code = languages.starter(BUDGET, Language.JAVA, "")
    assert "class Solution {" in code and "public int longestWithinBudget(int[] usage, int budget) {" in code


def test_cpp_starter_takes_vectors_by_reference() -> None:
    code = languages.starter(BOOKINGS, Language.CPP, "")
    assert "vector<vector<int>> mergeBookings(vector<vector<int>>& bookings) {" in code


def test_c_starter_follows_leetcodes_size_parameters() -> None:
    code = languages.starter(BOOKINGS, Language.C, "")
    assert (
        "int** mergeBookings(int** bookings, int bookingsSize, int* bookingsColSize, int* returnSize, "
        "int** returnColumnSizes) {" in code
    )
    assert "must be malloced" in code


def test_the_statement_uses_the_languages_names() -> None:
    md = "Write `longest_within_budget(usage, budget)`. Not longest_within_budgets."
    java = languages.statement(md, BUDGET, Language.JAVA)
    assert java == "Write `longestWithinBudget(usage, budget)`. Not longest_within_budgets."
    assert languages.statement(md, BUDGET, Language.PYTHON) == md


def test_case_input_is_integers_with_lengths_and_strings_as_character_codes() -> None:
    sig = FunctionSig(
        name="f",
        params=[Param(name="grid", type="list[list[int]]"), Param(name="words", type="list[str]")],
        returns="str",
    )
    assert languages.case_input(sig, [[[1, 2], [3]], ["ab", ""]]) == "2 2 1 2 1 3 2 2 97 98 0\n"


def test_a_type_only_python_has_is_refused() -> None:
    sig = FunctionSig(name="f", params=[Param(name="x", type="dict[str, int]")], returns="int")
    assert not languages.supports(sig)
    with pytest.raises(languages.UnsupportedSignature):
        languages.starter(sig, Language.JAVA, "")


def test_every_problem_can_be_solved_in_every_language() -> None:
    for spec in ProblemBank.load().matching(None, None):
        assert languages.supports(spec.function), spec.slug


def test_the_interviewer_is_told_the_language_and_sees_its_signature() -> None:
    spec = next(iter(ProblemBank.load().matching(None, None)))
    context = RubricContext.from_problem(spec, Language.CPP)
    assert context.fence == "cpp" and "writing C++" in context.brief_md
    assert languages.signature(spec.function, Language.CPP) in context.brief_md
    assert "writing" not in RubricContext.from_problem(spec).brief_md.split("Function to implement")[1]
