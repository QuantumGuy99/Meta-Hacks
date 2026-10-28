"""Live sessions: their sockets, phases and message routing (PLAN §9.1).

Each mode plugs in through a `ModeController` (coding/session.py, defense/controller.py), so the hub never
needs to know what a problem or a finding is.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal, Protocol

from pydantic import BaseModel

from crucible.contracts.common import Mode, Phase, Session, SessionConfig
from crucible.contracts.events import (
    CodeSnapshot,
    EditorEvent,
    SystemNote,
    TimelineEvent,
    TimelineKind,
    TranscriptTurn,
)
from crucible.contracts.report import CodingExtra, DefenseExtra, Report
from crucible.contracts.ws import (
    ChatSend,
    ClientMessage,
    EditorEvents,
    EditorSnapshot,
    ErrorMsg,
    Hello,
    HintRequest,
    PhaseAdvance,
    ReportReady,
    SessionEnd,
    SessionState,
    TranscriptUpdate,
)
from crucible.engine.analyzer import StructuredModel
from crucible.engine.codestate import CodeState
from crucible.engine.context import RubricContext
from crucible.engine.ids import new_id
from crucible.engine.live import LiveEngine
from crucible.engine.report import build_report
from crucible.engine.store import Store
from crucible.engine.timeline import Timeline
from crucible.engine.voice import Transcriber, VoiceBridge

logger = logging.getLogger(__name__)

IDLE_TTL_S = 600  # a runtime lives 10 min after its last socket closes (§9.1); longer than a report takes
FLUSH_INTERVAL_S = 0.25  # timeline writes are batched (§9.2)
FINISHED = frozenset({Phase.ENDED, Phase.REPORTING, Phase.REPORTED, Phase.FAILED})
# Only these moves may come from the browser (§8.2 phase.advance): "Start coding" and "I'm done".
CANDIDATE_ADVANCES = frozenset({(Phase.CLARIFY, Phase.CODING), (Phase.CODING, Phase.WRAP_UP)})
# After a session ends, the report builder (§9.8) moves it on; any live phase can end or fail.
_AFTER_END: dict[Phase, set[Phase]] = {
    Phase.ENDED: {Phase.REPORTING, Phase.FAILED},
    Phase.REPORTING: {Phase.REPORTED, Phase.FAILED},
}

InterviewerState = Literal["idle", "listening", "thinking", "speaking"]


class PhaseError(Exception):
    """A phase change that the mode doesn't allow."""


class ModeUnavailable(Exception):
    """No controller is registered for the requested mode yet."""


class SessionSetupError(Exception):
    """The session config can't be planned (an unknown problem or project, no problems at a difficulty)."""


@dataclass(frozen=True, slots=True)
class SessionPlan:
    problem_slug: str | None
    project_id: str | None
    time_limit_s: int


class ModeController(Protocol):
    """How a mode plugs into the hub. One instance per live session."""

    def allowed_transitions(self) -> Mapping[Phase, set[Phase]]: ...

    async def on_start(self, rt: "SessionRuntime") -> None:
        """First connect: run the opening phases."""
        ...

    async def on_resume(self, rt: "SessionRuntime") -> None:
        """A live session's runtime was reopened (after it expired): re-attach whatever was running."""
        ...

    async def on_client_message(self, rt: "SessionRuntime", msg: ClientMessage) -> bool:
        """Handle a message the hub doesn't (`code.run`, `defense.*`). False means unsupported."""
        ...

    async def on_timeline(self, rt: "SessionRuntime", event: TimelineEvent) -> None:
        """Called after every timeline event, e.g. a final transcript turn during the grill."""
        ...

    async def report_extra(self, rt: "SessionRuntime") -> CodingExtra | DefenseExtra: ...


class ModeFactory(Protocol):
    """What the hub is given for each mode: it plans new sessions and builds one controller per live session."""

    async def plan_session(self, config: SessionConfig) -> SessionPlan:
        """Pick the problem or project and the time limit. Raises `SessionSetupError` for a bad config."""
        ...

    def __call__(self) -> ModeController: ...


class Socket(Protocol):
    async def send_text(self, data: str) -> None: ...


class Connection:
    """One browser tab. Sends are serialized so concurrent broadcasts never interleave on a socket."""

    _ids: ClassVar[int] = 0

    def __init__(self, socket: Socket) -> None:
        Connection._ids += 1
        self.id = Connection._ids
        self._socket = socket
        self._lock = asyncio.Lock()

    async def send(self, message: BaseModel) -> None:
        async with self._lock:
            await self._socket.send_text(message.model_dump_json())


class SessionRuntime:
    """Everything live about one session: phase, timeline, code, sockets and its mode's controller."""

    def __init__(
        self,
        session: Session,
        controller: ModeController,
        store: Store,
        *,
        monotonic: Callable[[], float],
        wall: Callable[[], datetime],
        last_seq: int = 0,
        model: StructuredModel | None = None,
    ) -> None:
        self.session = session
        self.controller = controller
        self.code = CodeState()
        self.context: RubricContext | None = None
        self.last_context: RubricContext | None = None  # kept after detach, for the report
        self.interviewer_state: InterviewerState = "idle"
        self.voice: VoiceBridge | None = None  # opened by the first audio socket (§9.7)
        self.audio_socket: object | None = None  # the tab whose microphone feeds `voice`
        self.timeline = Timeline(session.id, store, self.now_ms, last_seq)
        self._model = model
        self._engine: LiveEngine | None = None
        self._store = store
        self._monotonic = monotonic
        self._wall = wall
        self._anchor: float | None = None  # monotonic time of session.started_at
        self._connections: dict[int, Connection] = {}
        self.sender: Connection | None = None  # the tab whose message the mode is handling right now
        self.resume_pending = False  # reopened after expiry; the mode resumes on the next connect
        self._phase_lock = asyncio.Lock()
        self._flusher: asyncio.Task[None] | None = None
        self._report_task: asyncio.Task[None] | None = None
        if session.started_at is not None:
            self._anchor_to(session.started_at)

    # --- time and state -----------------------------------------------------------------------------------

    def now_ms(self) -> int:
        """Ms since the session started (0 before it starts)."""
        return 0 if self._anchor is None else round((self._monotonic() - self._anchor) * 1000)

    def wall_now(self) -> datetime:
        return self._wall()

    async def set_interviewer_state(self, state: InterviewerState) -> None:
        if state != self.interviewer_state:
            self.interviewer_state = state
            await self.broadcast(self.state_message())

    def remaining_s(self) -> int | None:
        if self._anchor is None or self.session.phase in FINISHED or self.session.phase == Phase.SETUP:
            return None
        return max(0, self.session.time_limit_s - self.now_ms() // 1000)

    def state_message(self) -> SessionState:
        return SessionState(
            type="session.state",
            session=self.session,
            phase=self.session.phase,
            remaining_s=self.remaining_s(),
            interviewer_state=self.interviewer_state,
        )

    @property
    def live(self) -> bool:
        return self.session.phase not in FINISHED

    # --- lifecycle ----------------------------------------------------------------------------------------

    async def start(self) -> None:
        """First connect: stamp started_at and let the mode run its opening phases."""
        self.session.started_at = self._wall()
        self._anchor_to(self.session.started_at)
        await self._store.update_session(self.session)
        await self.controller.on_start(self)

    def start_flusher(self) -> None:
        if self._flusher is None:
            self._flusher = asyncio.create_task(self._flush_loop(), name=f"timeline-flush-{self.session.id}")

    async def close(self) -> None:
        # Optional mode hook: cancel the mode's own background tasks (timers, long stages).
        on_close = getattr(self.controller, "on_close", None)
        if on_close is not None:
            await on_close(self)
        await self.detach()
        if self.voice is not None:
            await self.voice.close()
        # A report cut short here restarts when someone next asks for it (SessionHub.report).
        for task in (self._report_task, self._flusher):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._report_task = None
        self._flusher = None
        await self.timeline.flush()

    def restore(self, events: list[TimelineEvent]) -> None:
        """Rebuild the code from earlier events when a runtime is reopened."""
        for event in events:
            if event.kind == TimelineKind.SNAPSHOT:
                self.code.apply_snapshot(CodeSnapshot.model_validate(event.payload))
            elif event.kind == TimelineKind.EDITOR:
                self.code.apply(EditorEvent.model_validate(event.payload))

    # --- phases -------------------------------------------------------------------------------------------

    async def set_phase(self, to: Phase, reason: str) -> None:
        """Move to `to` if the mode allows it, record it and tell every tab."""
        async with self._phase_lock:
            current = self.session.phase
            allowed = set(self.controller.allowed_transitions().get(current, set())) | _AFTER_END.get(
                current, set()
            )
            if current not in FINISHED:
                allowed |= {Phase.ENDED, Phase.FAILED}
            if to not in allowed:
                raise PhaseError(f"can't go from {current} to {to}")
            event = self.timeline.append(
                TimelineKind.PHASE, {"from_phase": current, "to_phase": to, "reason": reason}
            )
            self.session.phase = to
            if to == Phase.ENDED:
                self.session.ended_at = self._wall()
            await self._store.update_session(self.session)
        # Outside the lock, so a controller may change phase again from on_timeline.
        await self.controller.on_timeline(self, event)
        await self.broadcast(self.state_message())

    async def end(self, reason: str) -> None:
        if self.live:
            await self.set_phase(Phase.ENDED, reason)
        await self.detach()
        self.start_report()

    # --- the report (§9.8) --------------------------------------------------------------------------------

    def start_report(self) -> None:
        """Build the report in the background, once per ended session (a failed session gets none)."""
        running = self._report_task is not None and not self._report_task.done()
        if running or self.session.phase not in (Phase.ENDED, Phase.REPORTING):
            return
        self._report_task = asyncio.create_task(self._report(), name=f"report-{self.session.id}")

    async def _report(self) -> None:
        try:
            if self.session.phase == Phase.ENDED:
                await self.set_phase(Phase.REPORTING, "building the report")
            report = await build_report(self, self._model)
            await self._store.save_report(report)
            await self.set_phase(Phase.REPORTED, f"report ready ({report.model})")
            await self.broadcast(ReportReady(type="report.ready", session_id=self.session.id))
        except Exception:  # task boundary: say so on the timeline and stop, rather than hang in `reporting`
            logger.exception("report failed for %s", self.session.id)
            await self.note("error", "the report couldn't be built")
            await self.set_phase(Phase.FAILED, "report failed")

    # --- events -------------------------------------------------------------------------------------------

    async def record(
        self, kind: TimelineKind, payload: BaseModel | dict[str, Any], t: int | None = None
    ) -> TimelineEvent:
        """Append to the timeline first, then let the engine and the mode react (§9.1)."""
        event = self.timeline.append(kind, payload, t)
        if self._engine is not None:
            self._engine.on_event(event)
        await self.controller.on_timeline(self, event)
        return event

    async def note(self, level: Literal["info", "warning", "error"], message: str) -> None:
        logger.log(logging.WARNING if level != "info" else logging.INFO, "%s: %s", self.session.id, message)
        await self.record(TimelineKind.SYSTEM, SystemNote(level=level, message=message))

    async def attach(self, context: RubricContext) -> None:
        """Turn the analyzer and policy on for this rubric (coding at clarify, defense at fix).

        Without a model (tests, or no API key) the context is kept but nothing analyzes it.
        """
        await self.detach()
        self.context = self.last_context = context
        if self._model is not None:
            self._engine = LiveEngine(self, context, self._model)
            self._engine.start()

    def heard_speech(self) -> None:
        """Candidate speech in progress (a partial transcript): the policy holds unsolicited messages."""
        if self._engine is not None:
            self._engine.heard_speech()

    def asked(self, question: str) -> None:
        """A spoken question (Ask was held): the interviewer answers it like a typed one."""
        if self._engine is not None:
            self._engine.ask(question)

    async def detach(self) -> None:
        if self._engine is not None:
            await self._engine.stop()
            self._engine = None
        self.context = None

    # --- sockets ------------------------------------------------------------------------------------------

    def add(self, socket: Socket) -> Connection:
        connection = Connection(socket)
        self._connections[connection.id] = connection
        return connection

    def remove(self, connection: Connection) -> None:
        self._connections.pop(connection.id, None)

    @property
    def connected(self) -> bool:
        return bool(self._connections)

    async def send(self, connection: Connection, message: BaseModel) -> None:
        await connection.send(message)

    async def broadcast(self, message: BaseModel) -> None:
        for connection in list(self._connections.values()):
            try:
                await connection.send(message)
            except Exception:  # a closed tab must not stop the others
                logger.warning("dropping a socket for %s", self.session.id, exc_info=True)
                self.remove(connection)

    async def error(
        self, connection: Connection, code: str, message: str, *, retryable: bool = False
    ) -> None:
        await self.send(connection, ErrorMsg(type="error", code=code, message=message, retryable=retryable))

    # --- routing ------------------------------------------------------------------------------------------

    async def handle(self, connection: Connection, msg: ClientMessage) -> None:
        """Route one client message. Shared messages are handled here; the rest go to the mode."""
        match msg:
            case Hello():
                await self.send(connection, self.state_message())
            case EditorEvents(events=events):
                for event in events:
                    await self._editor_event(event)
            case EditorSnapshot(snapshot=snapshot):
                diverged = self.code.apply_snapshot(snapshot)
                await self.record(TimelineKind.SNAPSHOT, snapshot, t=snapshot.t)
                if diverged:
                    await self.note(
                        "warning", f"snapshot of {snapshot.file} v{snapshot.version} replaced the edits"
                    )
            case ChatSend(text=text):
                await self._chat(text)
            case HintRequest(step_id=step_id):
                if self._engine is None:
                    await self.error(connection, "unsupported", "hints aren't available right now")
                    return
                self._engine.request_hint(step_id)
            case PhaseAdvance(to=to):
                if (self.session.phase, to) not in CANDIDATE_ADVANCES:
                    await self.error(
                        connection, "bad_phase", f"can't move from {self.session.phase} to {to} here"
                    )
                    return
                await self.set_phase(to, "candidate")
            case SessionEnd():
                await self.end("ended by the candidate")
            case _:
                # The mode's handler can answer the tab that asked (`rt.sender`) instead of every tab.
                self.sender = connection
                try:
                    handled = await self.controller.on_client_message(self, msg)
                finally:
                    self.sender = None
                if not handled:
                    await self.error(connection, "unsupported", f"{msg.type} isn't available in this session")

    async def _editor_event(self, event: EditorEvent) -> None:
        applied = self.code.apply(event)
        await self.record(TimelineKind.EDITOR, event, t=event.t)
        if applied.desynced:
            await self.note(
                "warning",
                f"edit to {event.file} v{event.version} didn't fit the code; waiting for a snapshot",
            )

    async def _chat(self, text: str) -> None:
        now = self.now_ms()
        turn = TranscriptTurn(
            turn_id=new_id(),
            speaker="candidate",
            text=text,
            start_ms=now,
            end_ms=now,
            final=True,
            source="text",
        )
        await self.record(TimelineKind.TRANSCRIPT, turn)
        await self.broadcast(TranscriptUpdate(type="transcript.update", turn=turn))

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_INTERVAL_S)
            try:
                await self.timeline.flush()
            except Exception:
                logger.exception("timeline flush failed for %s; retrying", self.session.id)

    def _anchor_to(self, started_at: datetime) -> None:
        elapsed_s = (self._wall() - started_at).total_seconds()
        self._anchor = self._monotonic() - max(0.0, elapsed_s)


class SessionHub:
    """Creates sessions, opens and expires their runtimes, and connects sockets to them."""

    def __init__(
        self,
        store: Store,
        controllers: Mapping[Mode, ModeFactory],
        *,
        model: StructuredModel | None = None,
        asr: Transcriber | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        wall: Callable[[], datetime] = lambda: datetime.now(UTC),
        idle_ttl_s: float = IDLE_TTL_S,
    ) -> None:
        self.store = store
        self._asr = asr
        self.runtimes: dict[str, SessionRuntime] = {}
        self._controllers = controllers
        self._model = model
        self._monotonic = monotonic
        self._wall = wall
        self._idle_ttl_s = idle_ttl_s
        self._expiry: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def create_session(self, config: SessionConfig) -> Session:
        controller = self._controllers.get(config.mode)
        if controller is None:
            raise ModeUnavailable(f"{config.mode} sessions aren't available yet")
        plan = await controller.plan_session(config)
        session = Session(
            id=new_id(),
            config=config,
            phase=Phase.SETUP,
            created_at=self._wall(),
            started_at=None,
            ended_at=None,
            time_limit_s=plan.time_limit_s,
            problem_slug=plan.problem_slug,
            project_id=plan.project_id,
        )
        await self.store.create_session(session)
        return session

    async def get_session(self, session_id: str) -> Session | None:
        runtime = self.runtimes.get(session_id)
        return runtime.session.model_copy(deep=True) if runtime else await self.store.get_session(session_id)

    async def connect(self, session_id: str, socket: Socket) -> tuple[SessionRuntime, Connection]:
        """Attach a socket, opening the runtime if needed. The first connect starts the session."""
        runtime = await self.runtime(session_id)
        connection = runtime.add(socket)
        if runtime.session.phase == Phase.SETUP:
            await runtime.start()
        elif runtime.resume_pending:
            runtime.resume_pending = False
            await runtime.controller.on_resume(runtime)
        return runtime, connection

    async def disconnect(self, session_id: str, connection: Connection) -> None:
        runtime = self.runtimes.get(session_id)
        if runtime is None:
            return
        runtime.remove(connection)
        if not runtime.connected:
            self._schedule_expiry(session_id)

    async def end_session(self, session_id: str) -> Session:
        runtime = await self.runtime(session_id)
        await runtime.end("ended from the API")
        if not runtime.connected:
            self._schedule_expiry(session_id)
        return runtime.session.model_copy(deep=True)

    def voice(self, runtime: SessionRuntime) -> VoiceBridge | None:
        """The session's voice bridge, or None when transcription isn't configured (no API key)."""
        if runtime.voice is None and self._asr is not None:
            runtime.voice = VoiceBridge(runtime, self._asr)
        return runtime.voice

    async def report(self, session_id: str) -> Report | None:
        """The stored report, or None while there isn't one yet.

        A session left in `ended` or `reporting` with no report running (a restart cut it short) starts again.
        """
        report = await self.store.get_report(session_id)
        if report is not None:
            return report
        session = await self.get_session(session_id)
        if session is not None and session.phase in (Phase.ENDED, Phase.REPORTING):
            runtime = await self.runtime(session_id)
            runtime.start_report()
            if not runtime.connected:
                self._schedule_expiry(session_id)
        return None

    async def read_timeline(self, session_id: str) -> list[TimelineEvent]:
        runtime = self.runtimes.get(session_id)
        return await runtime.timeline.read() if runtime else await self.store.read_events(session_id)

    async def runtime(self, session_id: str) -> SessionRuntime:
        """The live runtime for a session, opened (and restored from the store) if needed."""
        async with self._lock:
            expiry = self._expiry.pop(session_id, None)
            if expiry is not None:
                expiry.cancel()
            runtime = self.runtimes.get(session_id)
            if runtime is not None:
                return runtime
            session = await self.store.get_session(session_id)
            if session is None:
                raise KeyError(session_id)
            controller = self._controllers.get(session.config.mode)
            if controller is None:
                raise ModeUnavailable(f"{session.config.mode} sessions aren't available yet")
            events = await self.store.read_events(session_id)
            runtime = SessionRuntime(
                session,
                controller(),
                self.store,
                monotonic=self._monotonic,
                wall=self._wall,
                last_seq=events[-1].seq if events else 0,
                model=self._model,
            )
            runtime.restore(events)
            runtime.start_flusher()
            # Resume once a socket is attached (in connect), so whatever the mode says reaches someone.
            runtime.resume_pending = runtime.live and session.phase != Phase.SETUP
            self.runtimes[session_id] = runtime
            return runtime

    async def close(self) -> None:
        """Flush and drop every runtime (app shutdown)."""
        for task in self._expiry.values():
            task.cancel()
        self._expiry.clear()
        for runtime in list(self.runtimes.values()):
            await runtime.close()
        self.runtimes.clear()

    def _schedule_expiry(self, session_id: str) -> None:
        previous = self._expiry.pop(session_id, None)
        if previous is not None:
            previous.cancel()
        self._expiry[session_id] = asyncio.create_task(self._expire(session_id), name=f"expire-{session_id}")

    async def _expire(self, session_id: str) -> None:
        await asyncio.sleep(self._idle_ttl_s)
        async with self._lock:
            self._expiry.pop(session_id, None)
            runtime = self.runtimes.get(session_id)
            if runtime is None or runtime.connected:
                return
            del self.runtimes[session_id]
        await runtime.close()
