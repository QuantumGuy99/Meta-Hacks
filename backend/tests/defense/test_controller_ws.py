"""Project Defense through the real WebSocket hub (DEF-6): audit → chaos → grill by chat → verify → verdict.

Local runner, real FastAPI app processes and real attacks; every model is down, so each stage takes its
fallback (flaws.json, the reference attack, keyword grading). ~2 s attacks keep each test to seconds.
"""

import json
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from crucible.contracts.common import Mode
from crucible.defense import audit as audit_mod
from crucible.defense.attack_writer import extract_functions, render_attack
from crucible.defense.audit import audit_from_flaws
from crucible.defense.controller import make_mode
from crucible.engine.api import router
from crucible.engine.hub import SessionHub
from crucible.engine.store import MemoryStore
from crucible.runner.local import LocalRunner
from tests.defense.fixtures import GOOD_ANSWER, WEAK_ANSWER, FakeLLM

pytestmark = pytest.mark.e2e
IDLE_TTL_S = 0.2
MESSAGE_LIMIT = 300


@pytest.fixture
def client(bank, local_settings) -> Iterator[TestClient]:
    audit_mod._CACHE.clear()
    mode = make_mode(
        local_settings,
        samples={bank.project.id: bank},
        runner=LocalRunner(local_settings),
        llm=FakeLLM(down=True),
        duration_override_s=2,
    )
    app = FastAPI()
    app.include_router(router)
    app.state.hub = SessionHub(MemoryStore(), {Mode.DEFENSE: mode}, idle_ttl_s=IDLE_TTL_S)
    with TestClient(app) as c:
        yield c


def start(client: TestClient, bank) -> str:
    r = client.post("/api/sessions", json={"mode": "defense", "project_id": bank.project.id})
    assert r.status_code == 201, r.text
    return r.json()["id"]


class Log:
    """Every message the socket received, so a test can also check what the browser was (not) sent."""

    def __init__(self, ws: Any) -> None:
        self.ws = ws
        self.seen: list[dict[str, Any]] = []

    def until(self, done: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        for _ in range(MESSAGE_LIMIT):
            message = self.ws.receive_json()
            self.seen.append(message)
            if done(message):
                return message
        raise AssertionError(f"never arrived; last types: {[m['type'] for m in self.seen[-10:]]}")


def typed(kind: str, **match: Any) -> Callable[[dict[str, Any]], bool]:
    return lambda m: m["type"] == kind and all(_get(m, k) == v for k, v in match.items())


def phase(name: str) -> Callable[[dict[str, Any]], bool]:
    return lambda m: m["type"] == "session.state" and m["phase"] == name


def _get(m: dict[str, Any], dotted: str) -> Any:
    for part in dotted.split("."):
        m = m.get(part) if isinstance(m, dict) else None
    return m


def through_grill(log: Log) -> dict[str, Any]:
    """Wait for the audit, the baseline that breaks, and the first grill question."""
    audit = log.until(typed("defense.audit"))
    assert audit["audit"]["findings"] and "explanation" not in audit["audit"]["findings"][0]
    done = log.until(typed("defense.chaos.done", **{"run.kind": "baseline"}))
    assert done["run"]["verdict"] == "broke", done["run"]["detail"]
    question = log.until(typed("interviewer.message"))
    assert (
        question["intervention"]["trigger"] == "grill" and "disappeared" in question["intervention"]["text"]
    )
    return done


def test_break_explain_fix_verify_pass(client, bank):
    session_id = start(client, bank)
    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        log = Log(ws)
        ws.send_json({"type": "hello", "client_now_ms": 0})
        through_grill(log)
        assert any(m["type"] == "defense.chaos.metric" for m in log.seen)

        ws.send_json({"type": "chat.send", "text": GOOD_ANSWER})
        graded = log.until(typed("defense.grill.eval"))
        assert graded["turn"]["root_cause_hit"] and graded["turn"]["score"] >= 6
        assert graded["finding"]["explanation"]  # revealed only now
        log.until(phase("fix"))

        ws.send_json({"type": "defense.verify", "finding_id": "f1", "files": bank.fixed_files})
        held = log.until(typed("defense.chaos.done", **{"run.kind": "verify"}))
        assert held["run"]["verdict"] == "held", held["run"]["detail"]
        verdict = log.until(typed("defense.verdict"))
        assert verdict["verdict"]["passed"], verdict["verdict"]["reasons"]
        log.until(phase("ended"))

    # The explanation never went out before the grill: not in any message before defense.grill.eval.
    before = log.seen[: next(i for i, m in enumerate(log.seen) if m["type"] == "defense.grill.eval")]
    assert all("explanation" not in str(m) for m in before)
    kinds = [e["kind"] for e in client.get(f"/api/sessions/{session_id}/timeline").json()]
    for k in ("audit", "chaos_metric", "chaos_run", "grill", "intervention", "verdict"):
        assert k in kinds


def test_weak_answer_gets_one_follow_up_then_counts_both(client, bank):
    session_id = start(client, bank)
    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        log = Log(ws)
        ws.send_json({"type": "hello", "client_now_ms": 0})
        through_grill(log)
        ws.send_json({"type": "chat.send", "text": WEAK_ANSWER})
        expected = audit_from_flaws(bank).findings[0]
        log.until(
            lambda m: (
                m["type"] == "interviewer.message" and m["intervention"]["text"] == expected.grill.follow_up
            )
        )
        # The answer key stays hidden until the grill is final: no eval, no explanation before the follow-up.
        assert not any(m["type"] == "defense.grill.eval" for m in log.seen)
        assert expected.explanation not in json.dumps(log.seen)

        ws.send_json({"type": "chat.send", "text": GOOD_ANSWER})
        second = log.until(typed("defense.grill.eval"))
        assert second["turn"]["follow_up_asked"] and second["turn"]["root_cause_hit"]
        assert len(second["turn"]["answer_turn_ids"]) == 2
        log.until(phase("fix"))


def test_verify_is_refused_during_the_grill(client, bank):
    session_id = start(client, bank)
    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        log = Log(ws)
        ws.send_json({"type": "hello", "client_now_ms": 0})
        through_grill(log)
        ws.send_json({"type": "defense.verify", "finding_id": "f1", "files": bank.fixed_files})
        assert log.until(typed("error"))["code"] == "bad_phase"


def test_unfixed_code_breaks_again_then_the_fix_passes(client, bank):
    session_id = start(client, bank)
    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        log = Log(ws)
        ws.send_json({"type": "hello", "client_now_ms": 0})
        through_grill(log)
        ws.send_json({"type": "chat.send", "text": GOOD_ANSWER})
        log.until(phase("fix"))

        ws.send_json({"type": "defense.verify", "finding_id": "f1", "files": {}})  # no edits
        again = log.until(typed("defense.chaos.done", **{"run.kind": "verify"}))
        assert again["run"]["verdict"] == "broke"
        log.until(phase("fix"))  # back to fix first, then the nudge
        nudge = log.until(typed("interviewer.message"))
        assert nudge["intervention"]["text"].startswith("Still breaking")

        ws.send_json({"type": "defense.verify", "finding_id": "f1", "files": bank.fixed_files})
        assert log.until(typed("defense.verdict"))["verdict"]["passed"]


def test_a_double_clicked_verify_runs_one_attack(client, bank):
    session_id = start(client, bank)
    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        log = Log(ws)
        ws.send_json({"type": "hello", "client_now_ms": 0})
        through_grill(log)
        ws.send_json({"type": "chat.send", "text": GOOD_ANSWER})
        log.until(phase("fix"))
        verify = {"type": "defense.verify", "finding_id": "f1", "files": bank.fixed_files}
        ws.send_json(verify)
        ws.send_json(verify)  # a second click while the first attack runs
        busy = log.until(typed("error"))
        assert busy["code"] == "busy", busy
        log.until(phase("ended"))
    runs = [e for e in client.get(f"/api/sessions/{session_id}/timeline").json() if e["kind"] == "chaos_run"]
    assert [r["payload"]["kind"] for r in runs] == ["baseline", "verify"]


def test_unknown_project_is_a_400(client):
    r = client.post("/api/sessions", json={"mode": "defense", "project_id": "nope"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_config"


def test_resumed_session_reasks_the_question_and_reuses_the_same_attack(client, bank):
    session_id = start(client, bank)
    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        log = Log(ws)
        ws.send_json({"type": "hello", "client_now_ms": 0})
        baseline = through_grill(log)
    time.sleep(IDLE_TTL_S * 5)  # the runtime expires; its state is gone from memory
    assert session_id not in client.app.state.hub.runtimes

    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        log = Log(ws)
        ws.send_json({"type": "hello", "client_now_ms": 0})
        assert log.until(typed("interviewer.message"))["intervention"]["trigger"] == "grill"
        ws.send_json({"type": "chat.send", "text": GOOD_ANSWER})
        log.until(phase("fix"))
        ws.send_json({"type": "defense.verify", "finding_id": "f1", "files": bank.fixed_files})
        held = log.until(typed("defense.chaos.done", **{"run.kind": "verify"}))
        assert held["run"]["verdict"] == "held"
        same = extract_functions(held["run"]["script"]) == extract_functions(baseline["run"]["script"])
        assert same, "verify must re-run the baseline's exact attack"


def test_extract_functions_round_trips_a_rendered_attack(bank):
    fn = bank.reference_attack.functions
    back = extract_functions(render_attack(fn, port=9, concurrency=5, duration_s=1))
    assert (back.setup_body.strip(), back.request_body.strip(), back.invariant_body.strip()) == (
        fn.setup_body.strip(),
        fn.request_body.strip(),
        fn.invariant_body.strip(),
    )
