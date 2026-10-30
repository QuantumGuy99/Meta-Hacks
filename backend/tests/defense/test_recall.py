"""Audit recall (DEF-2): matching rules, the ≥ 2 of 3 bar, and the flaws.json fallback never counts."""

import pytest

from crucible.defense.audit import audit_from_flaws
from crucible.defense.recall import EVALS_DIR, ExpectedFinding, audit_recall, load_eval, matched_flaws
from tests.defense.fixtures import FakeLLM

EXPECTED = [ExpectedFinding("f1", "app/main.py", 30, 45, "race_condition")]


def _finding(bank, **changes):
    return audit_from_flaws(bank).findings[0].model_copy(update=changes)


def test_overlapping_lines_in_the_same_file_and_category_match(bank):
    assert matched_flaws(EXPECTED, [_finding(bank, file="app/main.py", line_start=44, line_end=60)]) == {"f1"}


@pytest.mark.parametrize(
    "changes",
    [
        {"file": "app/other.py"},
        {"category": "blocking_io"},
        {"line_start": 46, "line_end": 60},
    ],
)
def test_a_different_file_category_or_disjoint_lines_dont_match(bank, changes):
    f = _finding(bank, **({"file": "app/main.py", "line_start": 30, "line_end": 45} | changes))
    assert matched_flaws(EXPECTED, [f]) == set()


def test_one_finding_counts_for_one_flaw_only(bank):
    twice = [*EXPECTED, ExpectedFinding("f2", "app/main.py", 40, 50, "race_condition")]
    f = _finding(bank, file="app/main.py", line_start=30, line_end=50)
    assert len(matched_flaws(twice, [f])) == 1


@pytest.mark.asyncio
async def test_two_of_three_runs_pass_and_the_fallback_never_counts(bank):
    from crucible.contracts.defense import AuditResult

    found = audit_from_flaws(bank)
    seeded = found.findings[0]
    expected = [ExpectedFinding("f1", seeded.file, seeded.line_start, seeded.line_end, seeded.category)]
    llm = FakeLLM(down=False)
    llm.push("audit", found)
    llm.push("audit", AuditResult(summary="", nodes=found.nodes, edges=found.edges, findings=[]))
    llm.push("audit", found)
    report = await audit_recall(bank, expected, llm, runs=3)
    assert report.hits == {"f1": 2} and report.passed()

    down = await audit_recall(bank, expected, FakeLLM(down=True), runs=3)
    assert down.hits == {"f1": 0} and not down.passed() and len(down.failed_runs) == 3


def test_every_p0_app_has_a_recall_eval():
    apps = {load_eval(p)[0] for p in EVALS_DIR.glob("*.json")}
    assert {"bank-transfer", "ticket-drop", "report-service"} <= apps
