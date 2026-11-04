"""Test harness: run a candidate's function against test cases (PLAN §12). Standard library only.

Reads one JSON object on stdin:
    {"code": str, "function": {"name": str, ...}, "cases": [{"id", "args", "expected", "comparator"}],
     "limits": {"per_test_s": float, "total_s": float, "stdout_bytes": int}, "hidden_case_ids": [str]}
Prints one JSON object: {"passed", "total", "cases": [CaseResult], "stdout", "stderr", "timed_out",
"compile_error"}. The runner adds run_id, t and kind to make a RunResult.

Runs in its own process (LocalRunner subprocess or a Modal sandbox); the runner also kills it after
total_s plus a margin, in case the candidate's code blocks inside C code where the timer can't fire.
"""

import contextlib
import copy
import io
import json
import math
import signal
import sys
import threading
import time
import traceback

REPR_LIMIT = 300
FLOAT_TOL = 1e-6


class CaseTimeout(Exception):
    pass


def main() -> None:
    req = json.loads(sys.stdin.read())
    result = run(req)
    sys.__stdout__.write(json.dumps(result))
    sys.__stdout__.flush()


def run(req: dict) -> dict:
    limits = {"per_test_s": 2.0, "total_s": 10.0, "stdout_bytes": 4096, **req.get("limits", {})}
    hidden = set(req.get("hidden_case_ids", []))
    cases = req["cases"]
    out, err = io.StringIO(), io.StringIO()
    result = {
        "passed": 0,
        "total": len(cases),
        "cases": [],
        "stdout": "",
        "stderr": "",
        "timed_out": False,
        "compile_error": None,
    }

    namespace = {"__name__": "solution"}
    try:
        code = compile(req["code"], "solution.py", "exec")
    except SyntaxError as exc:
        result["compile_error"] = f"line {exc.lineno}: {exc.msg}"
        return result
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), _alarm(limits["per_test_s"]):
            exec(code, namespace)
    except CaseTimeout:
        result["compile_error"] = "the module took too long to load"
        return _finish(result, out, err, limits)
    except BaseException as exc:
        result["compile_error"] = f"{type(exc).__name__} while loading: {exc}"
        return _finish(result, out, err, limits)
    fn = namespace.get(req["function"]["name"])
    if not callable(fn):
        result["compile_error"] = f"function {req['function']['name']!r} isn't defined"
        return _finish(result, out, err, limits)

    deadline = time.monotonic() + limits["total_s"]
    for case in cases:
        visible = case["id"] not in hidden
        if time.monotonic() >= deadline:
            result["timed_out"] = True
            result["cases"].append(_case(case, visible, False, None, "not run: total time limit reached", 0))
            continue
        per_test = min(limits["per_test_s"], max(deadline - time.monotonic(), 0.001))
        t0 = time.perf_counter()
        actual, error, passed = None, None, False
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), _alarm(per_test):
                actual = fn(*copy.deepcopy(case["args"]))
            passed = compare(case.get("comparator", "exact"), actual, case["expected"])
        except CaseTimeout:
            error = f"timed out after {per_test:g} s"
            result["timed_out"] = True
        except RecursionError:
            error = "RecursionError: maximum recursion depth exceeded"
        except BaseException as exc:
            error = _short_error(exc)
        ms = round((time.perf_counter() - t0) * 1000)
        result["cases"].append(_case(case, visible, passed, actual, error, ms))
        result["passed"] += passed
    return _finish(result, out, err, limits)


# --- comparators (PLAN §7.3) ------------------------------------------------------------------------------


def compare(comparator: str, actual, expected) -> bool:
    actual, expected = _jsonish(actual), _jsonish(expected)
    if comparator == "exact":
        return actual == expected
    if comparator == "float_tol":
        return _close(actual, expected)
    if comparator == "unordered":
        return isinstance(actual, list) and _sorted(actual) == _sorted(expected)
    if comparator == "unordered_inner":  # outer order matters, each inner list's order doesn't
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                isinstance(a, list) and _sorted(a) == _sorted(e)
                for a, e in zip(actual, expected, strict=True)
            )
        )
    if comparator == "set_of_lists":  # neither the outer nor the inner order matters
        return (
            isinstance(actual, list)
            and all(isinstance(a, list) for a in actual)
            and _sorted([_sorted(a) for a in actual]) == _sorted([_sorted(e) for e in expected])
        )
    raise ValueError(f"unknown comparator {comparator!r}")


def _jsonish(value):
    """What the value would look like after a JSON round trip: tuples and sets become lists."""
    if isinstance(value, (list, tuple)):
        return [_jsonish(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return _sorted([_jsonish(v) for v in value])
    if isinstance(value, dict):
        return {str(k): _jsonish(v) for k, v in value.items()}
    return value


def _sorted(values: list) -> list:
    return sorted(values, key=lambda v: json.dumps(v, sort_keys=True, default=repr))


def _close(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=FLOAT_TOL, abs_tol=FLOAT_TOL)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b, strict=True))
    return a == b


# --- helpers ------------------------------------------------------------------------------------------------


@contextlib.contextmanager
def _alarm(seconds: float):
    if not hasattr(signal, "SIGALRM"):  # Windows
        with _thread_alarm(seconds):
            yield
        return

    def _fire(signum, frame):
        raise CaseTimeout()

    previous = signal.signal(signal.SIGALRM, _fire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


@contextlib.contextmanager
def _thread_alarm(seconds: float):
    """Windows has no SIGALRM, so a timer thread raises SIGINT in this process instead. Like SIGALRM it
    stops a Python loop and wakes time.sleep, but not a blocked lock or other C code: the runner's
    process kill still covers those."""
    live = True

    def _fire(signum, frame):
        if live:  # dropped if it lands after the case has ended
            raise CaseTimeout()

    previous = signal.signal(signal.SIGINT, _fire)
    timer = threading.Timer(seconds, signal.raise_signal, (signal.SIGINT,))
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        live = False
        timer.cancel()
        timer.join()  # a timer that's already firing finishes first
        signal.signal(signal.SIGINT, previous)  # runs a pending SIGINT through _fire, which drops it


def _case(case: dict, visible: bool, passed: bool, actual, error, ms: int) -> dict:
    return {
        "id": case["id"],
        "visible": visible,
        "passed": bool(passed),
        "input_repr": _repr(case["args"]),
        "expected_repr": _repr(case["expected"]),
        "actual_repr": None if error else _repr(actual),
        "error": error,
        "runtime_ms": ms,
    }


def _short_error(exc: BaseException) -> str:
    """`TypeError: ... (line 7)` with the candidate's line number, never the harness's frames."""
    line = None
    for frame in traceback.extract_tb(exc.__traceback__):
        if frame.filename == "solution.py":
            line = frame.lineno
    where = f" (line {line})" if line else ""
    return f"{type(exc).__name__}: {exc}"[:REPR_LIMIT] + where


def _repr(value) -> str:
    text = repr(value)
    return text if len(text) <= REPR_LIMIT else text[: REPR_LIMIT - 1] + "…"


def _finish(result: dict, out: io.StringIO, err: io.StringIO, limits: dict) -> dict:
    cap = int(limits["stdout_bytes"])
    result["stdout"] = _cap(out.getvalue(), cap)
    result["stderr"] = _cap(err.getvalue(), cap)
    return result


def _cap(text: str, cap: int) -> str:
    data = text.encode()
    if len(data) <= cap:
        return text
    return data[:cap].decode(errors="ignore") + "\n… (truncated)"


if __name__ == "__main__":
    sys.setrecursionlimit(10_000)
    main()
