"""Profanity: detected on whole words, answered with a warning, a final warning, then the session ends."""

import pytest
from fastapi.testclient import TestClient

from crucible.engine.conduct import (
    FINAL_WARNING,
    STRIKES_TO_END,
    TERMINATED,
    TERMINATED_CODE,
    TERMINATED_REASON,
    WARNING,
    is_profane,
    response,
)
from tests.engine.test_hub_api import client, new_session, receive_until, state_in  # noqa: F401


@pytest.mark.parametrize(
    "text",
    [
        "what the fuck",
        "this is SHIT",
        "f*ck this",
        "sh1t",
        "fuuuck it",
        "you bastard",
        "shitty code",
        "WTF is this",
    ],
)
def test_profanity_is_caught_with_the_usual_disguises(text: str) -> None:
    assert is_profane(text)


@pytest.mark.parametrize(
    "text",
    [
        "Scunthorpe",
        "class Solution",
        "assess the cost",
        "cockpit",
        "cocktail",
        "Dickens",
        "shell script",
        "assume",
    ],
)
def test_ordinary_words_that_contain_one_are_not_profanity(text: str) -> None:
    assert not is_profane(text)


def test_a_warning_then_a_final_warning_then_the_end() -> None:
    assert [response(n) for n in range(1, STRIKES_TO_END + 1)] == [
        (WARNING, False),
        (FINAL_WARNING, False),
        (TERMINATED, True),
    ]
    assert "Repeated use will end this session" in WARNING


def lines(ws) -> str:
    return receive_until(ws, lambda m: m["type"] == "interviewer.message")["intervention"]["text"]


def test_repeated_profanity_ends_the_session_with_the_reason(client: TestClient) -> None:  # noqa: F811
    session = new_session(client)
    sid = session["id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        receive_until(ws, state_in("clarify"))
        ws.send_json({"type": "chat.send", "text": "this is shit"})
        assert lines(ws) == WARNING
        ws.send_json({"type": "chat.send", "text": "Can the list be empty?"})  # clean words are no strike
        ws.send_json({"type": "chat.send", "text": "what the fuck"})
        assert lines(ws) == FINAL_WARNING
        ws.send_json({"type": "chat.send", "text": "fuck this"})
        assert lines(ws) == TERMINATED
        error = receive_until(ws, lambda m: m["type"] == "error")
        assert (error["code"], error["message"], error["retryable"]) == (TERMINATED_CODE, TERMINATED, False)
        receive_until(ws, state_in("ended"))
    events = client.get(f"/api/sessions/{sid}/timeline").json()
    ends = [e for e in events if e["kind"] == "phase" and e["payload"]["to_phase"] == "ended"]
    assert ends[-1]["payload"]["reason"] == TERMINATED_REASON
    strikes = [e for e in events if e["kind"] == "system" and "profanity strike" in e["payload"]["message"]]
    assert len(strikes) == STRIKES_TO_END


def test_one_slip_only_warns_and_the_interview_goes_on(client: TestClient) -> None:  # noqa: F811
    session = new_session(client)
    with client.websocket_connect(f"/ws/sessions/{session['id']}") as ws:
        receive_until(ws, state_in("clarify"))
        ws.send_json({"type": "chat.send", "text": "damn, shit, sorry"})
        assert lines(ws) == WARNING
    assert client.get(f"/api/sessions/{session['id']}").json()["phase"] == "clarify"
