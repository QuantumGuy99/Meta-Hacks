"""The fix assistant (DEF-11, PLAN §11.9): code checks the model's edits, and every turn is on the timeline."""

import pytest

from crucible.contracts.defense import AssistantDraft, AssistantEdit
from crucible.defense.assistant import MAX_EDITS, UNAVAILABLE, check_draft
from tests.defense.fixtures import GOOD_ANSWER, FakeLLM
from tests.defense.test_controller_ws import Log, make_client, phase, start, through_grill, typed

FILES = {"app/main.py": "x = 1\n", "app/store.py": "y = 1\n"}


# --- code decides what the model's edits may touch ------------------------------------------------------------


def test_edits_to_unknown_files_and_no_op_edits_are_dropped() -> None:
    draft = AssistantDraft(
        text="  Add a lock.  ",
        edits=[
            AssistantEdit(path="app/main.py", content="x = 2\n"),
            AssistantEdit(path="app/main.py", content="x = 3\n"),  # a second edit to the same file
            AssistantEdit(path="app/store.py", content="y = 1\n"),  # changes nothing
            AssistantEdit(path="../etc/passwd", content="root\n"),  # not a project file
        ],
    )
    checked = check_draft(draft, FILES)
    assert checked.text == "Add a lock."
    assert [(e.path, e.content) for e in checked.edits] == [("app/main.py", "x = 2\n")]


def test_a_reply_carries_at_most_max_edits() -> None:
    files = {f"m{i}.py": "a\n" for i in range(MAX_EDITS + 3)}
    draft = AssistantDraft(text="", edits=[AssistantEdit(path=p, content="b\n") for p in files])
    assert len(check_draft(draft, files).edits) == MAX_EDITS


# --- over the session socket ------------------------------------------------------------------------------------


@pytest.fixture
def scripted():
    return FakeLLM(down=True)  # every model down except what a test pushes


@pytest.fixture
def client(bank, local_settings, scripted):
    yield from make_client(bank, local_settings, scripted)


def to_fix(client, bank):
    session_id = start(client, bank)
    ws_ctx = client.websocket_connect(f"/ws/sessions/{session_id}")
    ws = ws_ctx.__enter__()
    log = Log(ws)
    ws.send_json({"type": "hello", "client_now_ms": 0})
    through_grill(log)
    ws.send_json({"type": "chat.send", "text": GOOD_ANSWER})
    log.until(phase("fix"))
    return session_id, ws_ctx, ws, log


def test_ask_reply_and_apply_are_on_the_timeline(client, bank, scripted):
    fixed = bank.fixed_files["app/main.py"]
    scripted.push(
        "assistant",
        AssistantDraft(text="Hold a lock.", edits=[AssistantEdit(path="app/main.py", content=fixed)]),
    )
    session_id, ctx, ws, log = to_fix(client, bank)
    try:
        ws.send_json({"type": "assistant.ask", "text": "How do I fix this?", "files": {}})
        reply = log.until(typed("assistant.turn", **{"turn.kind": "reply"}))["turn"]
        assert reply["text"] == "Hold a lock." and [e["path"] for e in reply["edits"]] == ["app/main.py"]
        ws.send_json(
            {"type": "assistant.apply", "reply_id": reply["id"], "accepted": ["app/main.py", "app/x.py"]}
        )
        applied = log.until(typed("assistant.turn", **{"turn.kind": "apply"}))["turn"]
        assert applied["accepted"] == ["app/main.py"]
    finally:
        ctx.__exit__(None, None, None)
    turns = [
        e["payload"]
        for e in client.get(f"/api/sessions/{session_id}/timeline").json()
        if e["kind"] == "assistant"
    ]
    assert [t["kind"] for t in turns] == ["ask", "reply", "apply"]
    assert turns[2]["reply_to"] == reply["id"] and turns[2]["accepted"] == [
        "app/main.py"
    ]  # only what it proposed


def test_the_assistant_waits_for_the_grill(client, bank):
    session_id = start(client, bank)
    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        log = Log(ws)
        ws.send_json({"type": "hello", "client_now_ms": 0})
        through_grill(log)
        ws.send_json({"type": "assistant.ask", "text": "Just fix it", "files": {}})
        assert log.until(typed("error"))["code"] == "bad_phase"


def test_an_outage_says_so_and_the_session_goes_on(client, bank):
    _, ctx, ws, log = to_fix(client, bank)
    try:
        ws.send_json(
            {"type": "assistant.ask", "text": "Help?", "files": {}}
        )  # nothing pushed: the model is down
        reply = log.until(typed("assistant.turn", **{"turn.kind": "reply"}))["turn"]
        assert (
            reply["text"] == UNAVAILABLE and reply["edits"] == []
        )  # the question is answered, not left open
        ws.send_json({"type": "assistant.ask", "text": "Help?", "files": {"nope.py": "x\n"}})
        assert log.until(typed("error"))["code"] == "bad_request"  # files the project doesn't have
    finally:
        ctx.__exit__(None, None, None)
