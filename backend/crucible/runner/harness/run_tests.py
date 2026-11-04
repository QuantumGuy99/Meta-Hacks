"""Test harness: run a candidate's function against test cases (PLAN §12). Standard library only.

Reads one JSON object on stdin:
    {"code": str, "function": {"name": str, ...}, "cases": [{"id", "args", "expected", "comparator"}],
     "limits": {"per_test_s": float, "total_s": float, "stdout_bytes": int}, "hidden_case_ids": [str]}
With `"program"` (Java, C++, C; see runner/base.py `Program`) it writes the files, compiles them and runs the
program once for all cases, restarting it after a case that times out or crashes. Each case's result comes back
on stdout after RESULT_MARK as `<ms> <json>` or `<ms> !<error>`.

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
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import traceback

REPR_LIMIT = 300
FLOAT_TOL = 1e-6
RESULT_MARK = "\x1ecrucible-result\x1e"  # same as coding/languages.py
COMPILE_S = 10.0  # javac or g++ on a small sandbox
START_S = 2.0  # added to a process's first case: the JVM's start-up
COMPILE_ERROR_CHARS = 2000


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
    if req.get("program"):
        return run_program(req["program"], cases, hidden, limits, result)

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


# --- compiled languages ------------------------------------------------------------------------------------


def run_program(program: dict, cases: list, hidden: set, limits: dict, result: dict) -> dict:
    deadline = time.monotonic() + limits["total_s"]
    for name, text in program["files"].items():
        with open(name, "w", encoding="utf-8") as f:
            f.write(text)
    for command in program["compile"]:
        error = _compile(command, min(COMPILE_S, max(deadline - time.monotonic(), 0.001)))
        if error is not None:
            result["compile_error"] = error
            return result
    out, err = io.StringIO(), io.StringIO()
    i = 0
    while i < len(cases):
        i = _run_from(program, i, cases, hidden, limits, deadline, result, out, err)
    return _finish(result, out, err, limits)


def _compile(command: list, timeout_s: float):
    """None when it built, otherwise the compiler's message (paths trimmed) for the candidate."""
    try:
        done = subprocess.run(
            command, capture_output=True, timeout=timeout_s, check=False, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError:
        return f"{command[0]} isn't installed on this runner"
    except subprocess.TimeoutExpired:
        return f"compiling took longer than {timeout_s:g} s"
    if done.returncode == 0:
        return None
    text = (done.stderr or done.stdout).replace(os.getcwd() + os.sep, "").replace("./", "")
    # Their file is #included into our driver; the compiler's "included from main.cpp" line is noise.
    text = "\n".join(
        line for line in text.splitlines() if not line.startswith("In file included from")
    ).strip()
    return text[:COMPILE_ERROR_CHARS] or f"{command[0]} failed (exit {done.returncode})"


def _run_from(program, first, cases, hidden, limits, deadline, result, out, err) -> int:
    """Run cases[first:] in one process; return the index to restart from (len(cases) when done)."""
    if time.monotonic() >= deadline:
        _not_run(cases[first:], hidden, result)
        return len(cases)
    stdin = f"{len(cases) - first}\n" + "".join(program["inputs"][first:])
    proc = subprocess.Popen(
        program["run"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )
    lines: queue.Queue = queue.Queue()
    readers = [
        threading.Thread(target=_pump, args=(proc.stdout, lines), daemon=True),
        threading.Thread(target=_drain, args=(proc.stderr, err), daemon=True),
        threading.Thread(target=_feed, args=(proc.stdin, stdin), daemon=True),
    ]
    for reader in readers:
        reader.start()
    try:
        i, started = first, time.monotonic()
        while i < len(cases):
            budget = min(limits["per_test_s"] + (START_S if i == first else 0), deadline - time.monotonic())
            line = _next_result(lines, out, max(budget, 0.001))
            if line is None:  # no result in time
                if time.monotonic() >= deadline:
                    result["timed_out"] = True
                    _record(cases[i], hidden, result, None, f"timed out after {limits['per_test_s']:g} s", 0)
                    _not_run(cases[i + 1 :], hidden, result)
                    return len(cases)
                result["timed_out"] = True
                _record(cases[i], hidden, result, None, f"timed out after {limits['per_test_s']:g} s", 0)
                return i + 1
            if line == "":  # the process ended before this case's result
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(timeout=1)
                _record(
                    cases[i],
                    hidden,
                    result,
                    None,
                    _crash(proc.returncode),
                    round((time.monotonic() - started) * 1000),
                )
                return i + 1
            ms, _, value = line.partition(" ")
            if value.startswith("!"):
                _record(cases[i], hidden, result, None, value[1:][:REPR_LIMIT], int(ms))
            else:
                actual = json.loads(value)
                _record(cases[i], hidden, result, actual, None, int(ms))
            i += 1
            started = time.monotonic()
        return i
    finally:
        proc.kill()
        proc.wait()
        for reader in readers[:2]:
            reader.join(timeout=1)


def _pump(stream, lines: queue.Queue) -> None:
    for line in stream:
        lines.put(line)
    lines.put("")


def _drain(stream, err: io.StringIO) -> None:
    for line in stream:
        err.write(line)


def _feed(stream, text: str) -> None:
    try:
        stream.write(text)
        stream.close()
    except (BrokenPipeError, OSError):
        pass  # the program exited before reading every case


def _next_result(lines: queue.Queue, out: io.StringIO, timeout_s: float):
    """The next `<ms> <json>` result, keeping other output as stdout; None on timeout, "" at end of output."""
    until = time.monotonic() + timeout_s
    while True:
        try:
            line = lines.get(timeout=max(until - time.monotonic(), 0))
        except queue.Empty:
            return None
        if line == "":
            return ""
        before, mark, after = line.partition(RESULT_MARK)
        if not mark:
            out.write(line)
            continue
        if before:
            out.write(before + "\n")
        return after.rstrip("\n")


def _crash(code) -> str:
    if code is not None and code < 0:
        try:
            name = signal.Signals(-code).name
        except ValueError:
            name = f"signal {-code}"
        return {"SIGSEGV": "Segmentation fault (an out-of-bounds or null access)", "SIGABRT": "Aborted"}.get(
            name, f"crashed ({name})"
        )
    return f"the program exited (code {code}) before returning"


def _record(case, hidden, result, actual, error, ms) -> None:
    passed = error is None and compare(case.get("comparator", "exact"), actual, case["expected"])
    result["cases"].append(_case(case, case["id"] not in hidden, passed, actual, error, ms))
    result["passed"] += passed


def _not_run(cases, hidden, result) -> None:
    result["timed_out"] = True
    for case in cases:
        result["cases"].append(
            _case(case, case["id"] not in hidden, False, None, "not run: total time limit reached", 0)
        )


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
