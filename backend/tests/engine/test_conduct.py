"""Abusive language ends the interview on the spot, in both modes (engine/conduct.py, the hub's record())."""

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crucible.contracts.common import Phase
from crucible.contracts.events import IntegrityFlag, Intervention, TimelineKind, TranscriptTurn
from crucible.contracts.report import Report
from crucible.contracts.ws import ChatSend
from crucible.engine.conduct import (
    IMPROVEMENT,
    TERMINATED,
    TERMINATED_CODE,
    TERMINATED_REASON,
    crossed_line,
    failed_for_conduct,
)
from crucible.engine.prompts import CANNED
from crucible.engine.report import build_report
from tests.engine.test_hub_api import client, new_session, receive_until, state_in  # noqa: F401
from tests.engine.test_voice import Tab
from tests.factories import StubController, runtime


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
        "this is bullshit",
        "you're an idiot",
        "you are so useless",
        "you idiot",
        "this interview is garbage",
        "shut up and let me code",
        "f*** off",
        "[ __ ] this",
    ],
)
def test_abuse_and_profanity_cross_the_line(text: str) -> None:
    assert crossed_line(text)


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
        "you know, this approach is dumb, let me redo it",
        "my first solution was kind of stupid",
        "could you repeat the question?",
        "you're right, I missed the empty input",
        "the second write wins, so one update gets lost",
        "kill the process and retry with a fire retardant config",
    ],
)
def test_ordinary_talk_does_not(text: str) -> None:
    assert not crossed_line(text)


class Watching(StubController):
    """Keeps what the candidate said that reached the mode (to grade, or to answer)."""

    def __init__(self) -> None:
        self.heard: list[str] = []

    async def on_timeline(self, rt, event) -> None:
        if event.kind == TimelineKind.TRANSCRIPT:
            turn = TranscriptTurn.model_validate(event.payload)
            if turn.speaker == "candidate":
                self.heard.append(turn.text)


async def test_an_abusive_message_ends_the_interview_with_one_harsh_line() -> None:
    rt = runtime()
    rt.controller = Watching()
    tab = rt.add(Tab())
    await rt.handle(tab, ChatSend(type="chat.send", text="you're a useless clown, shut up"))
    await rt.handle(tab, ChatSend(type="chat.send", text="and fuck you too"))  # already over: no second line
    assert rt.session.phase not in (Phase.CLARIFY, Phase.CODING)
    events = await rt.timeline.read()
    [flag] = [IntegrityFlag.model_validate(e.payload) for e in events if e.kind == TimelineKind.INTEGRITY]
    lines = [Intervention.model_validate(e.payload) for e in events if e.kind == TimelineKind.INTERVENTION]
    assert flag.kind == "conduct"
    assert [(i.trigger, i.text) for i in lines] == [("conduct", CANNED["conduct"])]
    assert rt.controller.heard == []  # the mode never got it to grade or answer
    await asyncio.sleep(0)
    await rt.close()


async def test_the_report_of_such_an_interview_is_a_fail() -> None:
    rt = runtime()
    tab = rt.add(Tab())
    await rt.handle(tab, ChatSend(type="chat.send", text="fuck off"))
    report = await build_report(rt, None)
    assert report.overall == 0 and report.strengths == [] and report.improvements[0] == IMPROVEMENT
    assert "abusive language" in report.summary
    await rt.close()


def test_a_defense_report_fails_its_verdict_too() -> None:
    path = Path(__file__).parents[2] / "crucible/mock/fixtures/rest/report-defense.json"
    report = Report.model_validate(json.loads(path.read_text(encoding="utf-8"))["report"])
    failed = failed_for_conduct(report)
    assert failed.overall == 0 and failed.defense is not None and not failed.defense.verdict.passed
    assert failed.defense.verdict.reasons[0].startswith("Ended early for abusive language")


def test_over_the_socket_the_room_hears_the_line_and_gets_the_reason(client: TestClient) -> None:  # noqa: F811
    session = new_session(client)
    sid = session["id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        receive_until(ws, state_in("clarify"))
        ws.send_json({"type": "chat.send", "text": "this is shit"})
        line = receive_until(ws, lambda m: m["type"] == "interviewer.message")["intervention"]
        assert (line["trigger"], line["text"]) == ("conduct", CANNED["conduct"])
        error = receive_until(ws, lambda m: m["type"] == "error")
        assert (error["code"], error["message"], error["retryable"]) == (TERMINATED_CODE, TERMINATED, False)
        receive_until(ws, state_in("ended"))
    events = client.get(f"/api/sessions/{sid}/timeline").json()
    ends = [e for e in events if e["kind"] == "phase" and e["payload"]["to_phase"] == "ended"]
    assert ends[-1]["payload"]["reason"] == TERMINATED_REASON
