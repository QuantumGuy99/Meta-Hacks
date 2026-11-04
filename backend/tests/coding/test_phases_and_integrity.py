"""COD-2 (intro, phases, timers, wrap-up) and COD-4 (integrity notes), PLAN §10.1 and §10.4."""

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from crucible.coding.integrity import IntegrityDetector
from crucible.coding.problems import ProblemBank
from crucible.coding.session import CodingMode, new_lines
from crucible.config import Settings
from crucible.contracts.common import Mode
from crucible.contracts.events import EditorChange, EditorEvent
from crucible.engine.api import router
from crucible.engine.hub import SessionHub
from crucible.engine.store import MemoryStore
from crucible.runner.local import LocalRunner
from tests.factories import QUIET_STREAK_REFERENCE, write_quiet_streak

STARTER = "def longest_quiet_streak(readings: list[int], threshold: int) -> int:\n    pass\n"


def event(kind: str, t: int = 60_000, text: str = "", pasted: int | None = None) -> EditorEvent:
    changes = [EditorChange(range_offset=0, range_length=0, text=text)] if text else []
    return EditorEvent(t=t, version=2, kind=kind, changes=changes, pasted_chars=pasted)


# --- COD-4: integrity notes (pure) -----------------------------------------------------------------------


def test_a_multi_line_paste_is_noted_neutrally() -> None:
    flag = IntegrityDetector().observe(event("paste", t=374_000, text="a = 1\nb = 2\n"))
    assert flag is not None and flag.kind == "paste"
    assert flag.detail == "pasted 2 lines at 06:14"


def test_a_long_single_line_paste_counts_characters() -> None:
    flag = IntegrityDetector().observe(event("paste", text="x" * 45))
    assert flag is not None and flag.detail.startswith("pasted 45 characters")


def test_a_short_paste_is_not_noted() -> None:
    assert IntegrityDetector().observe(event("paste", text="best")) is None


def test_a_bulk_insert_without_a_paste_is_noted() -> None:
    flag = IntegrityDetector().observe(event("change", text="y" * 120))
    assert flag is not None and flag.kind == "bulk_insert" and flag.chars == 120


def test_typing_is_not_noted() -> None:
    assert IntegrityDetector().observe(event("change", text="for r in readings:")) is None


def test_a_tab_away_for_10_s_or_more_is_noted_with_its_duration() -> None:
    detector = IntegrityDetector()
    assert detector.observe(event("hidden", t=520_000)) is None
    flag = detector.observe(event("visible", t=534_000))
    assert flag is not None and flag.kind == "tab_hidden" and flag.duration_ms == 14_000
    assert flag.detail == "switched away for 14 s at 08:40" and flag.t == 520_000


def test_a_quick_tab_switch_is_not_noted() -> None:
    detector = IntegrityDetector()
    detector.observe(event("hidden", t=1_000))
    assert detector.observe(event("visible", t=5_000)) is None


def test_starter_lines_dont_count_as_new() -> None:
    assert new_lines(STARTER, STARTER) == 0
    assert new_lines(STARTER, STARTER + "    best = 0\n\n    cur = 0\n") == 2


# --- COD-2: phases, timers, wrap-up (end to end) ---------------------------------------------------------


@pytest.fixture
def local_settings() -> Settings:
    return Settings(
        _env_file=None,
        DATABASE_URL="sqlite:///:memory:",
        RUNNER="local",
        ALLOW_LOCAL_RUNNER=True,
        LOCAL_RUNNER_ISOLATE=False,
        MODEL_API_KEY="",
    )


@pytest.fixture
def make_client(tmp_path: Path, local_settings: Settings) -> Iterator[Callable[..., TestClient]]:
    write_quiet_streak(tmp_path)
    bank = ProblemBank.load(tmp_path)
    clients: list[TestClient] = []

    def build(**mode_kwargs: Any) -> TestClient:
        app = FastAPI()
        app.include_router(router)
        mode = CodingMode(bank, runner=lambda: LocalRunner(local_settings), **mode_kwargs)
        app.state.hub = SessionHub(MemoryStore(), {Mode.CODING: mode})
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield build
    for client in clients:
        client.__exit__(None, None, None)


def receive_until(ws: Any, done: Callable[[dict[str, Any]], bool], limit: int = 60) -> dict[str, Any]:
    for _ in range(limit):
        message = ws.receive_json()
        if done(message):
            return message
    raise AssertionError("expected message never arrived")


def in_phase(phase: str) -> Callable[[dict[str, Any]], bool]:
    return lambda m: m["type"] == "session.state" and m["phase"] == phase


def skip_warm_up(ws: Any) -> None:
    """Wait for the warm-up's greeting, press "Skip intro", then wait for clarify (the warm-up has its own tests)."""
    receive_until(
        ws, lambda m: m["type"] == "interviewer.message" and m["intervention"]["trigger"] == "warmup"
    )
    ws.send_json({"type": "phase.advance", "to": "clarify"})
    receive_until(ws, in_phase("clarify"))


def said(text_part: str) -> Callable[[dict[str, Any]], bool]:
    return lambda m: m["type"] == "interviewer.message" and text_part in m["intervention"]["text"]


def join(client: TestClient, **config: Any) -> tuple[str, Any]:
    body = {"mode": "coding", "problem_slug": "quiet-streak", **config}
    sid = client.post("/api/sessions", json=body).json()["id"]
    return sid, client.websocket_connect(f"/ws/sessions/{sid}")


def typed(t: int, version: int, offset: int, text: str) -> dict[str, Any]:
    change = {"range_offset": offset, "range_length": 0, "text": text}
    return {"t": t, "file": "solution.py", "version": version, "kind": "change", "changes": [change]}


def test_the_interviewer_greets_then_skip_intro_presents_the_problem_with_the_full_time(
    make_client: Callable[..., TestClient],
) -> None:
    _, socket = join(make_client())
    with socket as ws:
        greeting = receive_until(ws, lambda m: m["type"] == "interviewer.message")["intervention"]
        assert greeting["trigger"] == "warmup" and greeting["level"] == "question"
        ws.send_json({"type": "phase.advance", "to": "clarify"})
        state = receive_until(ws, in_phase("clarify"))
        intro = receive_until(ws, said("Here's your problem: Quiet Streak"))["intervention"]
        assert intro["trigger"] == "phase" and "20 minutes" in intro["text"]
        assert state["remaining_s"] >= 20 * 60 - 1  # the warm-up didn't use the problem's time


def test_three_new_lines_start_coding_and_two_dont(make_client: Callable[..., TestClient]) -> None:
    _, socket = join(make_client())
    with socket as ws:
        skip_warm_up(ws)
        ws.send_json(
            {
                "type": "editor.snapshot",
                "snapshot": {"t": 500, "file": "solution.py", "version": 1, "code": STARTER},
            }
        )
        end = len(STARTER)
        ws.send_json(
            {"type": "editor.events", "events": [typed(1000, 2, end, "    best = 0\n    cur = 0\n")]}
        )
        ws.send_json({"type": "hello", "client_now_ms": 0})
        assert receive_until(ws, lambda m: m["type"] == "session.state")["phase"] == "clarify"
        ws.send_json(
            {"type": "editor.events", "events": [typed(2000, 3, end + 25, "    for r in readings:\n")]}
        )
        receive_until(ws, in_phase("coding"))


def test_pastes_and_tab_switches_send_integrity_notes(make_client: Callable[..., TestClient]) -> None:
    _, socket = join(make_client())
    with socket as ws:
        skip_warm_up(ws)
        paste = {**typed(1000, 2, 0, "a = 1\nb = 2\n"), "kind": "paste", "pasted_chars": 12}
        hidden = {"t": 2000, "file": "solution.py", "version": 2, "kind": "hidden", "changes": []}
        visible = {**hidden, "t": 17000, "kind": "visible"}
        ws.send_json({"type": "editor.events", "events": [paste, hidden, visible]})
        first = receive_until(ws, lambda m: m["type"] == "integrity.flag")["flag"]
        second = receive_until(ws, lambda m: m["type"] == "integrity.flag")["flag"]
    assert (first["kind"], second["kind"]) == ("paste", "tab_hidden")
    assert "cheat" not in first["detail"] + second["detail"]


def test_im_done_runs_the_wrap_up_questions_then_ends(make_client: Callable[..., TestClient]) -> None:
    _, socket = join(make_client())
    with socket as ws:
        skip_warm_up(ws)
        ws.send_json({"type": "phase.advance", "to": "coding"})
        receive_until(ws, in_phase("coding"))
        ws.send_json({"type": "phase.advance", "to": "wrap_up"})
        receive_until(ws, said("let's wrap up"))
        receive_until(ws, said("time and space complexity"))
        ws.send_json({"type": "chat.send", "text": "O(n) time, O(1) space."})
        receive_until(ws, said("stream"))
        ws.send_json({"type": "chat.send", "text": "I'd keep the running count between readings."})
        receive_until(ws, said("end of the interview"))
        receive_until(ws, in_phase("ended"))


def test_a_passing_submit_opens_the_wrap_up_with_praise(make_client: Callable[..., TestClient]) -> None:
    _, socket = join(make_client())
    with socket as ws:
        skip_warm_up(ws)
        ws.send_json({"type": "phase.advance", "to": "coding"})
        receive_until(ws, in_phase("coding"))
        ws.send_json({"type": "code.submit", "file": "solution.py", "code": QUIET_STREAK_REFERENCE})
        receive_until(ws, in_phase("wrap_up"))
        receive_until(ws, said("passes every test"))


def test_the_time_limit_moves_to_wrap_up(make_client: Callable[..., TestClient]) -> None:
    _, socket = join(make_client(), time_limit_s=1)
    with socket as ws:
        skip_warm_up(ws)
        receive_until(ws, in_phase("wrap_up"))
        receive_until(ws, said("That's time"))


def test_an_unanswered_wrap_up_ends_after_its_limit(make_client: Callable[..., TestClient]) -> None:
    _, socket = join(make_client(wrap_up_limit_s=0.5))
    with socket as ws:
        skip_warm_up(ws)
        ws.send_json({"type": "phase.advance", "to": "coding"})
        receive_until(ws, in_phase("coding"))
        started = time.monotonic()
        ws.send_json({"type": "phase.advance", "to": "wrap_up"})
        receive_until(ws, in_phase("ended"))
    assert time.monotonic() - started < 5
