"""The test harness (RUN-1, PLAN §12): comparators, timeouts, errors and output caps, through LocalRunner."""

import signal

import pytest

from crucible.contracts.coding import CaseSpec, FunctionSig, Param
from crucible.runner.base import RunLimits, RunRequest
from crucible.runner.harness.run_tests import compare
from crucible.runner.local import LocalRunner

SIG = FunctionSig(name="solve", params=[Param(name="xs", type="list[int]")], returns="int")


def req(code: str, cases: list[CaseSpec], **kw) -> RunRequest:
    return RunRequest(run_id="r1", t=1234, kind="run", code=code, function=SIG, cases=cases, **kw)


def case(i: str, args: list, expected, comparator="exact") -> CaseSpec:
    return CaseSpec(id=i, args=args, expected=expected, comparator=comparator)


@pytest.mark.parametrize(
    ("comparator", "actual", "expected", "ok"),
    [
        ("exact", [1, 2], [1, 2], True),
        ("exact", (1, 2), [1, 2], True),  # tuples compare like their JSON form
        ("exact", [2, 1], [1, 2], False),
        ("unordered", [3, 1, 2], [1, 2, 3], True),
        ("unordered", [1, 1, 2], [1, 2, 2], False),
        ("float_tol", 0.1 + 0.2, 0.3, True),
        ("float_tol", [1.0000001, 2.0], [1.0, 2.0], True),
        ("float_tol", 1.01, 1.0, False),
        ("unordered_inner", [[2, 1], [4, 3]], [[1, 2], [3, 4]], True),
        ("unordered_inner", [[3, 4], [1, 2]], [[1, 2], [3, 4]], False),
        ("set_of_lists", [[4, 3], [2, 1]], [[1, 2], [3, 4]], True),
        ("set_of_lists", [[1, 2]], [[1, 2], [3, 4]], False),
        ("exact", {3, 1, 2}, [1, 2, 3], True),
    ],
)
def test_comparators(comparator, actual, expected, ok):
    assert compare(comparator, actual, expected) is ok


@pytest.fixture
def runner(local_settings) -> LocalRunner:
    return LocalRunner(local_settings)


async def test_passing_failing_and_hidden_cases(runner):
    code = "def solve(xs):\n    print('debug', len(xs))\n    return sum(xs)\n"
    cases = [case("v1", [[1, 2]], 3), case("v2", [[5]], 6), case("h1", [[]], 0)]
    r = await runner.run_tests("s", req(code, cases, hidden_case_ids=["h1"]))
    assert (r.run_id, r.t, r.kind, r.passed, r.total) == ("r1", 1234, "run", 2, 3)
    assert [c.passed for c in r.cases] == [True, False, True]
    assert [c.visible for c in r.cases] == [True, True, False]
    assert r.cases[1].actual_repr == "5" and r.cases[1].error is None
    assert "debug 2" in r.stdout and not r.timed_out and r.compile_error is None


async def test_compile_error_reports_the_line(runner):
    r = await runner.run_tests("s", req("def solve(xs)\n    return 1\n", [case("v1", [[1]], 1)]))
    assert r.compile_error and r.compile_error.startswith("line 1:") and r.passed == 0


async def test_missing_function_and_load_time_crash(runner):
    r = await runner.run_tests("s", req("def other(xs):\n    return 1\n", [case("v1", [[1]], 1)]))
    assert "isn't defined" in (r.compile_error or "")
    r = await runner.run_tests("s", req("raise ValueError('boom')\n", [case("v1", [[1]], 1)]))
    assert "ValueError" in (r.compile_error or "")


async def test_exception_points_at_the_candidates_line(runner):
    code = "def solve(xs):\n    total = 0\n    return xs[10]\n"
    r = await runner.run_tests("s", req(code, [case("v1", [[1]], 1)]))
    assert r.cases[0].error.startswith("IndexError") and r.cases[0].error.endswith("(line 3)")


async def test_per_test_timeout_then_later_cases_still_run(runner):
    code = "def solve(xs):\n    if xs == [0]:\n        while True:\n            pass\n    return len(xs)\n"
    cases = [case("slow", [[0]], 1), case("fast", [[1, 2]], 2)]
    r = await runner.run_tests("s", req(code, cases, limits=RunLimits(per_test_s=0.3, total_s=5)))
    assert r.timed_out and "timed out" in r.cases[0].error and r.cases[1].passed


async def test_per_test_timeout_wakes_a_sleeping_case(runner):
    code = "import time\ndef solve(xs):\n    if xs == [0]:\n        time.sleep(30)\n    return len(xs)\n"
    cases = [case("slow", [[0]], 1), case("fast", [[1, 2]], 2)]
    r = await runner.run_tests("s", req(code, cases, limits=RunLimits(per_test_s=0.3, total_s=5)))
    assert r.timed_out and "timed out" in r.cases[0].error and r.cases[1].passed
    assert "stopped" not in r.stderr  # the per-test timer ended it, not the process kill


async def test_total_limit_skips_the_rest(runner):
    code = "import time\ndef solve(xs):\n    time.sleep(0.25)\n    return 0\n"
    cases = [case(f"c{i}", [[i]], 0) for i in range(6)]
    r = await runner.run_tests("s", req(code, cases, limits=RunLimits(per_test_s=1, total_s=0.6)))
    assert r.timed_out and any("total time limit" in (c.error or "") for c in r.cases)


async def test_stdout_is_capped(runner):
    code = "def solve(xs):\n    print('x' * 10000)\n    return 0\n"
    r = await runner.run_tests("s", req(code, [case("v1", [[1]], 0)], limits=RunLimits(stdout_bytes=100)))
    assert len(r.stdout) < 200 and r.stdout.endswith("(truncated)")


async def test_code_that_blocks_the_timer_is_killed(runner):
    # time.sleep in C under a blocked SIGALRM: only the process-level kill can stop it.
    code = (
        "import signal, time\nsignal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})\n"
        "def solve(xs):\n    time.sleep(30)\n"
    )
    if not hasattr(signal, "SIGALRM"):  # Windows: the timer arrives as SIGINT, which this code ignores
        code = (
            "import signal, time\n"
            "def solve(xs):\n    signal.signal(signal.SIGINT, signal.SIG_IGN)\n    time.sleep(30)\n"
        )
    r = await runner.run_tests(
        "s", req(code, [case("v1", [[1]], 0)], limits=RunLimits(per_test_s=0.2, total_s=0.5))
    )
    assert r.timed_out and "stopped" in r.stderr
