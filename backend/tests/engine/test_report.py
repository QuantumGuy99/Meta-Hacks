"""ENG-8: the end-of-session report (PLAN §9.8, §7.5)."""

import json
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from crucible.coding.problems import ProblemBank
from crucible.coding.session import CodingMode
from crucible.contracts.coding import Analysis, ProblemSpec
from crucible.contracts.common import Mode, Phase, Session, SessionConfig
from crucible.contracts.defense import AuditResult
from crucible.contracts.events import (
    CaseResult,
    EditorChange,
    EditorEvent,
    IntegrityFlag,
    Intervention,
    InterventionLevel,
    InterventionTrigger,
    PhaseChange,
    RunResult,
    TimelineEvent,
    TimelineKind,
    TranscriptTurn,
)
from crucible.contracts.report import CodingExtra, DefenseExtra, Metrics, Report, ReportDraft
from crucible.engine.api import router
from crucible.engine.context import RubricContext
from crucible.engine.hub import SessionHub
from crucible.engine.report import (
    MAX_MOMENTS,
    TEMPLATE_MODEL,
    build_report,
    compute_metrics,
    draft_messages,
    longest_silence,
    merge,
    pick_moments,
    template_draft,
)
from crucible.engine.store import MemoryStore
from tests.factories import (
    FAKE_MODEL_ID,
    FIXTURES,
    FakeModel,
    analysis,
    problem_json,
    runtime,
    write_quiet_streak,
)

DRAFT = json.loads((FIXTURES / "report_draft.json").read_text())
DEFENSE = DefenseExtra.model_validate(json.loads((FIXTURES / "report_defense.json").read_text())["defense"])
CODING = CodingExtra(problem_slug="quiet-streak", steps=[], approach=None, complexity_answer_ok=None)
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


# --- building timelines -------------------------------------------------------------------------------------


def events(*items: tuple[int, TimelineKind, BaseModel | dict[str, Any]]) -> list[TimelineEvent]:
    return [
        TimelineEvent(
            seq=i,
            t=t,
            kind=kind,
            payload=p.model_dump(mode="json") if isinstance(p, BaseModel) else p,
        )
        for i, (t, kind, p) in enumerate(items, start=1)
    ]


def phase(t: int, to: Phase, frm: Phase = Phase.SETUP) -> tuple[int, TimelineKind, BaseModel]:
    return t, TimelineKind.PHASE, PhaseChange(from_phase=frm, to_phase=to, reason="test")


def edit(
    t: int, kind: str = "change", text: str = "x", pasted: int | None = None
) -> tuple[int, TimelineKind, BaseModel]:
    changes = [EditorChange(range_offset=0, range_length=0, text=text)] if kind in ("change", "paste") else []
    return (
        t,
        TimelineKind.EDITOR,
        EditorEvent(t=t, version=t, kind=kind, changes=changes, pasted_chars=pasted),
    )


def turn(
    t: int, text: str, speaker: str = "candidate", end: int | None = None, source: str = "text"
) -> tuple:
    payload = TranscriptTurn(
        turn_id=f"tt{t}", speaker=speaker, text=text, start_ms=t, end_ms=end or t, final=True, source=source
    )
    return t, TimelineKind.TRANSCRIPT, payload


def run(
    t: int, kind: str = "run", visible: tuple[int, int] = (2, 2), hidden: tuple[int, int] = (0, 0)
) -> tuple:
    def case(i: int, is_visible: bool, passed: bool) -> CaseResult:
        return CaseResult(
            id=f"c{i}",
            visible=is_visible,
            passed=passed,
            input_repr=None,
            expected_repr=None,
            actual_repr=None,
            error=None,
            runtime_ms=1,
        )

    cases = [case(i, True, i < visible[0]) for i in range(visible[1])]
    cases += [case(100 + i, False, i < hidden[0]) for i in range(hidden[1])]
    result = RunResult(
        run_id=f"r{t}",
        t=t,
        kind=kind,
        passed=visible[0] + hidden[0],
        total=visible[1] + hidden[1],
        cases=cases,
        stdout="",
        stderr="",
        timed_out=False,
        compile_error=None,
    )
    return t, TimelineKind.RUN, result


def said(
    t: int,
    level: InterventionLevel = InterventionLevel.NUDGE,
    trigger: InterventionTrigger = InterventionTrigger.MISSED_STEP,
    *,
    step_id: str | None = "s1",
    suppressed: bool = False,
    text: str = "What should an empty list give you?",
) -> tuple:
    payload = Intervention(
        id=f"i{t}",
        t=t,
        trigger=trigger,
        level=level,
        text=text,
        step_id=step_id,
        speak=False,
        suppressed=suppressed,
    )
    return t, TimelineKind.INTERVENTION, payload


def analysed(t: int, s1: str = "not_started", s2: str = "in_progress") -> tuple:
    return t, TimelineKind.ANALYSIS, Analysis.model_validate(analysis(s1, s2, proposal=False))


def flag(t: int, kind: str = "paste") -> tuple:
    payload = IntegrityFlag(
        id=f"f{t}", t=t, kind=kind, detail=f"pasted 3 lines at {t}", chars=90, duration_ms=None
    )
    return t, TimelineKind.INTEGRITY, payload


# A coding session: clarify at 0, coding at 60 s, wrap-up at 600 s, ended at 700 s.
SESSION = events(
    phase(0, Phase.CLARIFY, Phase.INTRO),
    turn(20_000, "Can the list be empty?"),
    edit(30_000, "change", "def f():"),
    phase(60_000, Phase.CODING, Phase.CLARIFY),
    analysed(70_000),
    said(80_000),
    said(90_000, InterventionLevel.HINT, step_id="s2"),
    said(95_000, InterventionLevel.NUDGE, suppressed=True),  # passive: never seen, never counted
    said(96_000, InterventionLevel.INFO, InterventionTrigger.PHASE, step_id=None),  # a phase line
    edit(100_000, "paste", "abc", pasted=40),
    flag(100_000),
    edit(110_000, "hidden"),
    edit(140_000, "visible"),
    run(200_000, visible=(1, 2)),
    analysed(250_000, s1="done"),
    run(300_000, visible=(2, 2)),
    turn(310_000, "It works now", end=315_000, source="voice"),
    run(500_000, "submit", visible=(2, 2), hidden=(7, 8)),
    phase(600_000, Phase.WRAP_UP, Phase.CODING),
    turn(605_000, "What's the time complexity?", speaker="interviewer"),
    turn(620_000, "Linear, one pass."),
    phase(700_000, Phase.ENDED, Phase.WRAP_UP),
)


# --- metrics ------------------------------------------------------------------------------------------------


def test_metrics_come_from_the_timeline() -> None:
    m = compute_metrics(SESSION, 700_000)
    assert (m.duration_s, m.time_to_first_edit_s, m.time_to_first_run_s) == (700, 30, 200)
    assert (m.runs, m.submits, m.hidden_passed, m.hidden_total) == (2, 1, 7, 8)
    assert m.interventions_shown == 2  # the suppressed nudge and the phase line don't count
    assert m.hints_by_level == {"nudge": 1, "question": 0, "hint": 1, "concept": 0}
    assert (m.chars_typed, m.chars_pasted, m.tab_hidden_s, m.talk_time_s) == (8, 40, 30, 5)
    # 315 s → 500 s: no talking, typing or runs (the submit at 500 s ends it).
    assert m.longest_silence_s == 185


def test_no_submit_means_no_hidden_results() -> None:
    m = compute_metrics(events(phase(0, Phase.CODING), run(10_000)), 20_000)
    assert (m.hidden_passed, m.hidden_total, m.submits, m.runs) == (None, None, 0, 1)


def test_silence_only_counts_while_the_candidate_is_expected_to_act() -> None:
    timeline = events(
        phase(0, Phase.AUDIT),
        phase(300_000, Phase.GRILL, Phase.AUDIT),  # five quiet minutes of audit and chaos don't count
        turn(310_000, "It's a race."),
        phase(320_000, Phase.VERIFY, Phase.GRILL),
    )
    assert longest_silence(timeline, 900_000) == (10_000, 300_000)


def test_a_tab_still_hidden_at_the_end_counts_to_the_end() -> None:
    m = compute_metrics(events(phase(0, Phase.CODING), edit(10_000, "hidden")), 70_000)
    assert m.tab_hidden_s == 60


# --- moments ------------------------------------------------------------------------------------------------


def test_moments_cover_the_session_in_time_order() -> None:
    picks = pick_moments(SESSION, 700_000, {"s1": "Clarify the input", "s2": "Track the run"})
    titles = [p.title for p in picks]
    assert titles == [
        "Started coding",
        "Stated a plan",
        "Nudge from the interviewer",
        "Hint from the interviewer",
        "Pasted code",
        "First passing run",
        "Longest silence",
        "Submitted",
        "Wrap-up answer",
    ]
    assert [p.t for p in picks] == sorted(p.t for p in picks)
    nudge = picks[2]
    assert nudge.kind == "nudge" and "Clarify the input" in nudge.facts
    assert "done 170 s later" in nudge.facts  # the s1 nudge at 80 s, s1 done at 250 s
    assert "wasn't done by the end" in picks[3].facts  # s2 never finished
    assert picks[7].kind == "issue" and "9 of 10 tests passed" in picks[7].facts
    assert 'Answered: "Linear, one pass."' in picks[8].facts


def test_moments_are_capped_keeping_the_most_important() -> None:
    timeline = events(
        phase(0, Phase.CODING),
        edit(1_000),
        *(
            said(10_000 + i * 1_000, InterventionLevel.NUDGE, InterventionTrigger.IDLE, step_id=None)
            for i in range(20)
        ),
        run(80_000, visible=(2, 2)),
        run(90_000, "submit", hidden=(3, 3)),
    )
    picks = pick_moments(timeline, 100_000, {})
    assert len(picks) == MAX_MOMENTS
    assert {"Started coding", "Submitted", "First passing run"} <= {p.title for p in picks}


def test_a_final_submit_that_first_passes_is_one_moment() -> None:
    timeline = events(
        phase(0, Phase.CODING), run(10_000, visible=(1, 2)), run(20_000, "submit", hidden=(3, 3))
    )
    titles = [p.title for p in pick_moments(timeline, 30_000, {})]
    assert titles.count("Submitted") == 1 and "First passing run" not in titles


def test_defense_moments_cover_chaos_grill_and_verdict() -> None:
    audit = AuditResult.model_validate(json.loads((FIXTURES / "audit_result.json").read_text()))
    timeline = events(
        (1_000, TimelineKind.AUDIT, audit),
        (2_000, TimelineKind.CHAOS_RUN, DEFENSE.chaos_runs[0]),
        (3_000, TimelineKind.GRILL, DEFENSE.grill[0]),
        (4_000, TimelineKind.CHAOS_RUN, DEFENSE.chaos_runs[1]),
        (5_000, TimelineKind.VERDICT, DEFENSE.verdict),
    )
    picks = pick_moments(timeline, 6_000, {})
    assert [(p.title, p.kind) for p in picks] == [
        ("Broke under load", "issue"),
        ("Grill answer", "good"),  # scored 7/10
        ("Fix held", "good"),
        ("Verdict", "good"),
    ]
    assert "Balance transfers under load" in picks[0].facts
    assert "scored 7/10, named the root cause" in picks[1].facts


# --- merge: code decides --------------------------------------------------------------------------------------


def coding_metrics(**overrides: Any) -> Metrics:
    return compute_metrics(SESSION, 700_000).model_copy(update=overrides)


def test_measured_scores_replace_the_models_and_overall_is_their_mean() -> None:
    draft = ReportDraft.model_validate(DRAFT)  # the model says correctness 7
    picks = pick_moments(SESSION, 700_000, {})
    report = merge("s1", Mode.CODING, draft, coding_metrics(), picks, CODING, "muse-wonder", NOW)
    scores = {d.name: d.score for d in report.dimensions}
    assert scores["correctness"] == 9  # 7 of 8 hidden tests, measured
    assert [d.name for d in report.dimensions] == [
        "problem_solving",
        "correctness",
        "code_quality",
        "communication",
        "independence",
    ]  # the mode's order; the model scored no "debugging"
    assert report.overall == round(sum(scores.values()) / len(scores) * 10)
    assert report.model == "muse-wonder" and report.coding == CODING and report.defense is None


def test_moments_keep_codes_times_and_kinds_with_the_models_words() -> None:
    picks = pick_moments(SESSION, 700_000, {})
    worded = {
        **DRAFT,
        "moments": [
            {"t": picks[0].t, "kind": "issue", "title": "You began", "detail": "First keystroke.", "tip": ""},
            {"t": 999, "kind": "good", "title": "Invented", "detail": "Not in the session.", "tip": None},
        ],
    }
    report = merge(
        "s1", Mode.CODING, ReportDraft.model_validate(worded), coding_metrics(), picks, CODING, "m", NOW
    )
    assert [m.t for m in report.moments] == [p.t for p in picks]
    first = report.moments[0]
    assert (first.kind, first.title, first.tip) == ("milestone", "You began", None)  # code's kind; "" → None
    assert report.moments[1].detail == picks[1].facts  # unworded: the facts as they are
    assert all(m.title != "Invented" for m in report.moments)


def test_lists_are_trimmed_to_three() -> None:
    draft = ReportDraft.model_validate({**DRAFT, "strengths": ["a", " ", "b", "c", "d"]})
    report = merge("s1", Mode.CODING, draft, coding_metrics(), [], CODING, "m", NOW)
    assert report.strengths == ["a", "b", "c"]


def test_defense_scores_come_from_the_verdict_and_the_grill() -> None:
    draft = ReportDraft.model_validate(
        {
            **DRAFT,
            "dimensions": [
                {"name": "system_understanding", "score": 2, "evidence": "model"},
                {"name": "correctness", "score": 1, "evidence": "model"},
                {"name": "communication", "score": 7, "evidence": "model"},
            ],
        }
    )
    metrics = coding_metrics(hidden_passed=None, hidden_total=None)
    report = merge("s1", Mode.DEFENSE, draft, metrics, [], DEFENSE, "m", NOW)
    scores = {d.name: d.score for d in report.dimensions}
    v = DEFENSE.verdict
    fixed = len(v.findings_fixed) / (len(v.findings_fixed) + len(v.findings_unfixed))
    assert scores == {
        "system_understanding": round(v.avg_grill_score),
        "correctness": round(10 * fixed),
        "communication": 7,
    }
    assert report.defense == DEFENSE and report.coding is None


# --- the template report ---------------------------------------------------------------------------------------


def test_the_template_uses_only_measurements() -> None:
    picks = pick_moments(SESSION, 700_000, {})
    draft = template_draft(coding_metrics(), picks, CODING, SESSION)
    scores = {d.name: d.score for d in draft.dimensions}
    assert scores == {"correctness": 9, "independence": 6}  # 10 − 1 nudge − 2.5 for the hint, rounded
    assert [m.detail for m in draft.moments] == [p.facts for p in picks]
    assert draft.strengths == [] and draft.improvements == []


@pytest.mark.parametrize(
    ("timeline", "expected"),
    [
        (events(phase(0, Phase.CODING), run(10_000, visible=(1, 4))), 2),  # last run's visible tests
        (events(phase(0, Phase.CODING)), 0),  # nothing run
    ],
)
def test_without_a_submit_the_template_scores_correctness_from_the_last_run(
    timeline: list[TimelineEvent], expected: int
) -> None:
    metrics = compute_metrics(timeline, 20_000)
    draft = template_draft(metrics, [], CODING, timeline)
    assert {d.name: d.score for d in draft.dimensions}["correctness"] == expected


# --- the prompt ---------------------------------------------------------------------------------------------------


def test_the_prompt_carries_metrics_moments_and_the_conversation() -> None:
    rt = runtime()
    rt.code.code_by_file["solution.py"] = "def longest_quiet_streak(readings, threshold):\n    return 0\n"
    metrics = compute_metrics(SESSION, 700_000)
    picks = pick_moments(SESSION, 700_000, {})
    messages = draft_messages(rt, SESSION, 700_000, metrics, picks, CODING, None)
    prompt = messages[1]["content"]
    assert '"hidden_passed": 7' in prompt
    assert all(f'"t": {p.t}' in prompt for p in picks)
    assert "candidate: Can the list be empty?" in prompt
    assert "return 0" in prompt and "Voice: on" in prompt
    assert "Walk the list once" in prompt  # step history from the analyses


@pytest.mark.parametrize(
    ("ok", "verdict"),
    [(True, "matched an acceptable"), (False, "did not match"), (None, "not graded")],
)
def test_the_prompt_carries_the_complexity_verdict_code_decided(ok: bool | None, verdict: str) -> None:
    extra = CODING.model_copy(update={"approach": "single pass", "complexity_answer_ok": ok})
    messages = draft_messages(
        runtime(), SESSION, 700_000, compute_metrics(SESSION, 700_000), [], extra, QUIET_STREAK
    )
    prompt = messages[1]["content"]
    assert "Approach: single pass" in prompt and f"Complexity answer: {verdict}" in prompt


# --- the final analysis -----------------------------------------------------------------------------------------


QUIET_STREAK = RubricContext.from_problem(ProblemSpec.model_validate(problem_json()))


@pytest.mark.asyncio
async def test_code_changed_since_the_last_analysis_is_analyzed_before_the_report() -> None:
    model = ReportingModel(DRAFT)
    model.replies = [analysis(s1="done", s2="done", proposal=False)]
    rt = runtime(model)
    rt.last_context = QUIET_STREAK
    rt.code.code_by_file["solution.py"] = "def longest_quiet_streak(readings, threshold):\n    return 0\n"
    await build_report(rt, model)
    analyses = await rt.timeline.read({TimelineKind.ANALYSIS})
    assert len(analyses) == 1 and [s["status"] for s in analyses[0].payload["steps"]] == ["done", "done"]
    assert "Phase: clarify" in model.calls[0][-1]["content"]  # the analyzer's own prompt, on the final code


@pytest.mark.asyncio
async def test_unchanged_code_isnt_analyzed_again() -> None:
    model = ReportingModel(DRAFT)
    rt = runtime(model)
    rt.last_context = QUIET_STREAK
    rt.code.code_by_file["solution.py"] = "def f():\n    return 0\n"
    rt.code.mark_analyzed()
    await build_report(rt, model)
    assert model.calls == [] and await rt.timeline.read({TimelineKind.ANALYSIS}) == []


# --- end to end through the API ---------------------------------------------------------------------------------


class ReportingModel(FakeModel):
    """The analyzer gets an analysis; the report gets `draft` (or raises it)."""

    def __init__(self, draft: dict[str, Any] | Exception) -> None:
        super().__init__(analysis(proposal=False))
        self.draft = draft
        self.report_calls = 0

    async def complete_json_with_model[T: BaseModel](
        self,
        role: str,
        messages: Sequence[Mapping[str, Any]],
        schema: type[T],
        *,
        session_id: str | None = None,
    ) -> tuple[T, str]:
        self.report_calls += 1
        if isinstance(self.draft, Exception):
            raise self.draft
        return schema.model_validate(self.draft), FAKE_MODEL_ID


def make_client(tmp_path: Path, model: FakeModel | None, store: MemoryStore | None = None) -> TestClient:
    write_quiet_streak(tmp_path)
    app = FastAPI()
    app.include_router(router)
    modes = {Mode.CODING: CodingMode(ProblemBank.load(tmp_path), warm_up=False)}
    app.state.hub = SessionHub(store or MemoryStore(), modes, model=model)
    return TestClient(app)


def receive_until(ws: Any, done: Callable[[dict[str, Any]], bool], limit: int = 40) -> dict[str, Any]:
    for _ in range(limit):
        message = ws.receive_json()
        if done(message):
            return message
    raise AssertionError("expected message never arrived")


def poll_report(client: TestClient, sid: str, timeout_s: float = 5) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while True:
        response = client.get(f"/api/sessions/{sid}/report")
        if response.status_code == 200:
            return response.json()
        assert response.status_code == 202, response.text
        assert response.json() == {"status": "generating"}
        if time.monotonic() > deadline:
            raise AssertionError("report never arrived")
        time.sleep(0.02)


def end_session(client: TestClient, sid: str) -> None:
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        receive_until(ws, lambda m: m["type"] == "session.state" and m["phase"] == "clarify")
        ws.send_json({"type": "chat.send", "text": "Can the readings list be empty?"})
        ws.send_json({"type": "session.end"})
        receive_until(ws, lambda m: m["type"] == "report.ready")


def new_session(client: TestClient) -> str:
    return client.post("/api/sessions", json={"mode": "coding", "problem_slug": "quiet-streak"}).json()["id"]


def system_notes(client: TestClient, sid: str) -> list[str]:
    runtime = client.app.state.hub.runtimes[sid]
    return [e.payload["message"] for e in client.portal.call(runtime.timeline.read, {TimelineKind.SYSTEM})]


def test_an_ended_session_gets_a_report_and_report_ready(tmp_path: Path) -> None:
    model = ReportingModel(DRAFT)
    with make_client(tmp_path, model) as client:
        sid = new_session(client)
        end_session(client, sid)
        report = Report.model_validate(poll_report(client, sid))
        assert client.get(f"/api/sessions/{sid}").json()["phase"] == "reported"
    assert report.model == FAKE_MODEL_ID and report.mode == Mode.CODING
    assert report.summary == DRAFT["summary"]
    assert report.coding is not None and report.coding.problem_slug == "quiet-streak"
    assert report.coding.approach == "single pass with a running count"  # from the analyses (COD-5)
    assert model.report_calls == 1


def test_a_model_failure_still_produces_the_template_report(tmp_path: Path) -> None:
    with make_client(tmp_path, ReportingModel(RuntimeError("wonder and spark are down"))) as client:
        sid = new_session(client)
        end_session(client, sid)
        report = Report.model_validate(poll_report(client, sid))
        notes = system_notes(client, sid)
    assert report.model == TEMPLATE_MODEL
    assert {d.name for d in report.dimensions} == {"correctness", "independence"}
    assert any("report model didn't answer" in n for n in notes)


def test_without_a_model_the_template_report_is_built(tmp_path: Path) -> None:
    with make_client(tmp_path, None) as client:
        sid = new_session(client)
        end_session(client, sid)
        assert poll_report(client, sid)["model"] == TEMPLATE_MODEL


def test_a_live_session_has_no_report_yet(tmp_path: Path) -> None:
    with make_client(tmp_path, None) as client:
        sid = new_session(client)
        response = client.get(f"/api/sessions/{sid}/report")
        assert response.status_code == 409 and response.json()["error"]["code"] == "session_live"
        assert client.get("/api/sessions/nope/report").status_code == 404


def test_a_failed_session_has_no_report(tmp_path: Path) -> None:
    store = MemoryStore()
    session = Session(
        id="failed1",
        config=SessionConfig(mode="coding", problem_slug="quiet-streak"),
        phase=Phase.FAILED,
        created_at=NOW,
        started_at=NOW,
        ended_at=None,
        time_limit_s=1200,
        problem_slug="quiet-streak",
        project_id=None,
    )
    with make_client(tmp_path, None, store) as client:
        client.portal.call(store.create_session, session)
        response = client.get("/api/sessions/failed1/report")
    assert response.status_code == 404 and response.json()["error"]["code"] == "report_unavailable"


def test_a_report_cut_short_by_a_restart_starts_again_when_asked_for(tmp_path: Path) -> None:
    store = MemoryStore()
    ended = Session(
        id="ended1",
        config=SessionConfig(mode="coding", problem_slug="quiet-streak"),
        phase=Phase.REPORTING,  # the server stopped while it was building
        created_at=NOW,
        started_at=NOW,
        ended_at=NOW,
        time_limit_s=1200,
        problem_slug="quiet-streak",
        project_id=None,
    )
    with make_client(tmp_path, ReportingModel(DRAFT), store) as client:
        client.portal.call(store.create_session, ended)
        report = poll_report(client, "ended1")
        assert client.get("/api/sessions/ended1").json()["phase"] == "reported"
    assert report["session_id"] == "ended1" and report["model"] == FAKE_MODEL_ID
