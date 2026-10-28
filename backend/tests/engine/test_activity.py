"""The "Under the hood" strip (docs/STORY.md): model.activity from the wrapper, the hub and the voice bridge."""

import asyncio
import json
from typing import Any

import openai
import pytest

from crucible.contracts.events import InterventionText, TimelineKind
from crucible.engine.activity import TASKS, display_name, to_activity
from crucible.engine.hub import SessionHub
from crucible.engine.store import MemoryStore
from crucible.engine.voice import VoiceBridge
from crucible.models.asr import ASRError
from crucible.models.llm import CallActivity
from crucible.models.registry import SPARK, SPARK_CONTRIBUTOR, SPARK_OPEN, WONDER
from tests.engine.test_voice import FakeASR, FakeStream, Setup, chunk_reply, complete, start, until
from tests.factories import StubController, runtime
from tests.models.test_llm import HANG, MESSAGES, OK, FakeClient, Verdict, http_error, make_llm


class Watcher:
    def __init__(self) -> None:
        self.seen: list[CallActivity] = []

    async def __call__(self, activity: CallActivity) -> None:
        self.seen.append(activity)

    def statuses(self) -> list[tuple[str, str | None]]:
        return [(a.status, a.model) for a in self.seen]


# --- the wrapper: one started and one end per call --------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_call_reports_started_then_done_and_retries_add_nothing() -> None:
    meta = FakeClient({SPARK: [http_error(openai.RateLimitError, 429), OK]})  # one retry inside the call
    wrapper, _, _ = make_llm({"meta": meta})
    watcher = Watcher()
    wrapper.watch(watcher)
    await wrapper.complete_json("analyzer", MESSAGES, Verdict, session_id="s1")
    assert watcher.statuses() == [("started", SPARK), ("done", SPARK)]
    started, done = watcher.seen
    assert started.call_id == done.call_id and started.session_id == "s1" and started.latency_ms is None
    assert done.latency_ms is not None and done.latency_ms >= 0


@pytest.mark.asyncio
async def test_a_backup_model_answering_is_a_fallback() -> None:
    meta = FakeClient({WONDER: [http_error(openai.BadRequestError, 400)], SPARK: [OK]})
    wrapper, _, _ = make_llm({"meta": meta})
    watcher = Watcher()
    wrapper.watch(watcher)
    await wrapper.complete_json_with_model("report", MESSAGES, Verdict)
    assert watcher.statuses() == [("started", WONDER), ("fallback", SPARK)]


@pytest.mark.asyncio
async def test_every_model_failing_is_failed() -> None:
    meta = FakeClient(
        {WONDER: [http_error(openai.BadRequestError, 400)], SPARK: [http_error(openai.BadRequestError, 400)]}
    )
    wrapper, _, _ = make_llm({"meta": meta})
    watcher = Watcher()
    wrapper.watch(watcher)
    with pytest.raises(Exception, match="every model failed"):
        await wrapper.complete_json("report", MESSAGES, Verdict)
    assert watcher.statuses() == [("started", WONDER), ("failed", WONDER)]


@pytest.mark.asyncio
async def test_a_call_cancelled_midway_is_stopped_not_left_working() -> None:
    wrapper, _, _ = make_llm({"meta": FakeClient({SPARK: [HANG]})})
    watcher = Watcher()
    wrapper.watch(watcher)
    call = asyncio.create_task(wrapper.complete_json("analyzer", MESSAGES, Verdict, session_id="s1"))
    await until(lambda: bool(watcher.seen))
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    assert watcher.statuses() == [("started", SPARK), ("stopped", SPARK)]


@pytest.mark.asyncio
async def test_a_failing_watcher_never_breaks_the_call() -> None:
    wrapper, _, _ = make_llm({"meta": FakeClient({SPARK: [OK]})})

    async def broken(activity: CallActivity) -> None:
        raise RuntimeError("the strip is down")

    wrapper.watch(broken)
    assert await wrapper.complete_json("analyzer", MESSAGES, Verdict) == OK


# --- labels -------------------------------------------------------------------------------------------------------


def call(role: str = "analyzer", model: str | None = SPARK, provider: str | None = "meta") -> CallActivity:
    return CallActivity("c1", role, "s1", "done", provider, model, 1200)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("model", "provider", "name"),
    [
        (SPARK, "meta", "Muse Spark"),
        (SPARK_CONTRIBUTOR, "meta", "Muse Spark"),
        (WONDER, "meta", "Muse Wonder"),
        (SPARK_OPEN, "baseten", "Muse Spark Open"),
    ],
)
def test_chips_use_display_names_never_model_ids(model: str, provider: str, name: str) -> None:
    assert display_name(call(model=model, provider=provider)) == name


def test_every_role_has_a_plain_task_label() -> None:
    from crucible.models.registry import ROLES

    assert set(ROLES) <= set(TASKS)
    activity = to_activity(call("report", WONDER), t=5_000)
    assert (activity.model_name, activity.task, activity.status, activity.latency_ms, activity.t) == (
        "Muse Wonder",
        "writing your report",
        "done",
        1200,
        5_000,
    )


# --- the hub: only sessions open here, with the real wrapper feeding it ------------------------------------------


class Tab:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_text(self, data: str) -> None:
        self.sent.append(json.loads(data))


@pytest.mark.asyncio
async def test_the_hub_shows_a_sessions_calls_and_keeps_them_for_the_replay() -> None:
    wrapper, _, _ = make_llm({"meta": FakeClient({SPARK: [InterventionText(text="hi")] * 3})})
    hub = SessionHub(MemoryStore(), {}, model=wrapper)  # the hub starts watching the model it's given
    rt = runtime()
    hub.runtimes[rt.session.id] = rt
    tab = Tab()
    rt.add(tab)
    await wrapper.complete_json("interviewer", MESSAGES, InterventionText, session_id=rt.session.id)
    await wrapper.complete_json("interviewer", MESSAGES, InterventionText, session_id="someone-else")
    await wrapper.complete_json("interviewer", MESSAGES, InterventionText)  # no session: offline work
    shown = [m["activity"] for m in tab.sent if m["type"] == "model.activity"]
    assert [(a["model_name"], a["task"], a["status"]) for a in shown] == [
        ("Muse Spark", "answering your question", "started"),
        ("Muse Spark", "answering your question", "done"),
    ]
    stored = rt.timeline.tail([TimelineKind.MODEL_ACTIVITY])
    assert [e.payload["status"] for e in stored] == ["started", "done"]


def test_a_hub_without_a_watchable_model_still_works() -> None:
    SessionHub(MemoryStore(), {}, model=None)
    SessionHub(MemoryStore(), {}, model=StubController())  # type: ignore[arg-type]


# --- Muse Voice ------------------------------------------------------------------------------------------------


def voice_activity(s: Setup) -> list[tuple[str, str, int | None]]:
    return [
        (m["activity"]["task"], m["activity"]["status"], m["activity"]["latency_ms"])
        for m in s.tab.messages
        if m["type"] == "model.activity"
    ]


@pytest.mark.asyncio
async def test_speaking_lights_muse_voice_listening() -> None:
    stream = FakeStream({1: [start(1, 0)], 3: [complete(1, "Can it be empty?", 1_500)]})
    s = Setup(FakeASR(stream))
    s.bridge.start()
    await until(lambda: s.bridge.streaming)
    await s.frames(3)
    await until(lambda: len(voice_activity(s)) == 2)
    assert voice_activity(s) == [("listening", "started", None), ("listening", "done", 1_500)]
    assert all(m["activity"]["model_name"] == "Muse Voice" for m in s.tab.of("model.activity"))


@pytest.mark.asyncio
async def test_each_fallback_chunk_shows_as_transcribing() -> None:
    reply = chunk_reply((0, 900, "Hello."))
    s = Setup(FakeASR(ASRError("policy", code=1008), transcriptions=(reply, ASRError("down"))))
    s.bridge.start()
    await until(lambda: s.bridge.state == "chunked")
    await s.frames(250)  # two 10 s chunks: one answered, one failed
    await until(lambda: len(voice_activity(s)) == 4)
    assert sorted(status for task, status, _ in voice_activity(s) if task == "transcribing") == [
        "done",
        "failed",
        "started",
        "started",
    ]


def test_voice_bridge_is_importable_with_activity() -> None:
    assert VoiceBridge  # the bridge imports the strip labels without a cycle
