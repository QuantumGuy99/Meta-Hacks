"""DefenseController: Project Defense in a live session, on the engine's ModeController hook (PLAN §11.2).

The hub owns sockets, phases and the timeline; DefensePipeline owns the stages. This file connects them:
- on start, audit and attack in the background, then ask the first grill question;
- during the grill, each final candidate turn (chat or voice) answers the current finding;
- `defense.verify` re-runs the same attack against the edited files; the verdict ends the session.

Long stages (audit, chaos, verify: seconds to a minute) never run inside the socket handler. One stage runs
at a time; a message that arrives meanwhile gets a retryable `busy` error.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Mapping

from pydantic import BaseModel

from crucible.config import Settings, get_settings
from crucible.contracts.common import Phase, SessionConfig
from crucible.contracts.defense import AuditResult, ChaosRun, GrillTurn, RaceReplay
from crucible.contracts.events import (
    Intervention,
    InterventionLevel,
    InterventionTrigger,
    ModelActivity,
    PhaseChange,
    TimelineEvent,
    TimelineKind,
    TranscriptTurn,
)
from crucible.contracts.report import DefenseExtra
from crucible.contracts.ws import (
    ClientMessage,
    DefenseAudit,
    DefenseChaosDone,
    DefenseChaosMetric,
    DefenseGrillEval,
    DefenseReplay,
    DefenseRunChaos,
    DefenseVerdict,
    DefenseVerify,
    ErrorMsg,
    InterviewerMessage,
)
from crucible.defense import verdict as verdict_mod
from crucible.defense.attack_writer import extract_functions
from crucible.defense.audit import AuditFailed
from crucible.defense.chaos import run_attack
from crucible.defense.grill import SAFE_FEEDBACK, grill_question
from crucible.defense.model_client import WrapperModelClient
from crucible.defense.pipeline import MAX_FIX_ROUNDS, DefensePipeline
from crucible.defense.ports import ModelClient
from crucible.defense.projects import Sample, load_samples
from crucible.engine.context import RubricContext
from crucible.engine.hub import SessionPlan, SessionRuntime, SessionSetupError
from crucible.engine.ids import new_id
from crucible.engine.interviewer import looks_like_code
from crucible.engine.timeline import public_audit
from crucible.runner import Runner, RunnerError, make_runner

logger = logging.getLogger(__name__)

DEFAULT_TIME_LIMIT_S = 30 * 60
TRANSITIONS: dict[Phase, set[Phase]] = {
    Phase.SETUP: {Phase.AUDIT},
    Phase.AUDIT: {Phase.CHAOS, Phase.VERDICT},
    Phase.CHAOS: {Phase.GRILL, Phase.VERDICT},
    Phase.GRILL: {Phase.FIX, Phase.VERIFY},
    Phase.FIX: {Phase.VERIFY, Phase.VERDICT},
    Phase.VERIFY: {Phase.FIX, Phase.VERDICT},
    Phase.VERDICT: {Phase.ENDED},
}
FIX_PROMPT = "Over to you: fix it in the editor, then press Verify. I'll run the exact same attack again."


class DefenseMode:
    """The hub's ModeFactory for defense: plans sessions from the sample apps, builds one controller each."""

    def __init__(
        self,
        samples: Mapping[str, Sample],
        runner: Runner | Callable[[], Runner],
        llm: ModelClient,
        *,
        duration_override_s: int | None = None,
    ) -> None:
        """`runner` may be a factory, built on first use: missing Modal credentials then fail a defense
        session at creation (400) instead of failing app startup."""
        self.samples = samples
        self._runner = runner
        self.llm = llm
        self.duration_override_s = duration_override_s

    @property
    def runner(self) -> Runner:
        if not hasattr(self._runner, "start_project"):
            self._runner = self._runner()
        return self._runner

    async def plan_session(self, config: SessionConfig) -> SessionPlan:
        try:
            _ = self.runner
        except RunnerError as exc:
            raise SessionSetupError(f"Project Defense can't run code right now: {exc}") from exc
        if not config.project_id:
            raise SessionSetupError("Pick a project to defend.")
        if config.project_id not in self.samples:
            raise SessionSetupError(f"There's no project called {config.project_id}.")
        return SessionPlan(
            problem_slug=None,
            project_id=config.project_id,
            time_limit_s=config.time_limit_s or DEFAULT_TIME_LIMIT_S,
        )

    def __call__(self) -> DefenseController:
        return DefenseController(self)


def make_mode(
    settings: Settings | None = None,
    *,
    samples: Mapping[str, Sample] | None = None,
    runner: Runner | None = None,
    llm: ModelClient | None = None,
    duration_override_s: int | None = None,
) -> DefenseMode:
    """What main.py registers for Mode.DEFENSE. Tests inject samples, a runner and a fake model."""
    s = settings or get_settings()
    if samples is None:
        samples = load_samples(s.DEFENSE_APPS_DIR, s.DEFENSE_EXTRA_APPS_DIR)
    return DefenseMode(
        samples,
        runner or (lambda: make_runner(s)),
        llm or WrapperModelClient(),
        duration_override_s=duration_override_s,
    )


class HubSink:
    """EventSink for a live session: record on the timeline, then send the matching server message."""

    def __init__(self, rt: SessionRuntime) -> None:
        self.rt = rt

    async def emit(self, kind: TimelineKind, payload: BaseModel, *, public: BaseModel | None = None) -> None:
        if kind == TimelineKind.MODEL_ACTIVITY and isinstance(payload, ModelActivity):
            # The strip's own path records and broadcasts it, stamped with the session clock.
            await self.rt.show_activity(payload.model_copy(update={"t": self.rt.now_ms()}))
            return
        await self.rt.record(kind, payload)
        message: BaseModel | None = None
        if kind == TimelineKind.AUDIT and isinstance(payload, AuditResult):
            message = DefenseAudit(type="defense.audit", audit=public_audit(payload))
        elif kind == TimelineKind.CHAOS_METRIC:
            message = DefenseChaosMetric(type="defense.chaos.metric", metric=payload)
        elif kind == TimelineKind.CHAOS_RUN:
            message = DefenseChaosDone(type="defense.chaos.done", run=payload)
        elif kind == TimelineKind.REPLAY:
            message = DefenseReplay(type="defense.replay", replay=payload)
        elif kind == TimelineKind.VERDICT:
            message = DefenseVerdict(type="defense.verdict", verdict=payload)
        if message is not None:
            await self.rt.broadcast(message)


class DefenseController:
    def __init__(self, mode: DefenseMode) -> None:
        self.mode = mode
        self.pipeline: DefensePipeline | None = None
        self._lock = asyncio.Lock()  # one stage at a time
        # Set when an attack task is spawned, before it can take the lock: a second Verify or re-run sent in
        # the meantime would otherwise pass the `locked()` check and queue a second attack.
        self._attack_pending = False
        self._tasks: set[asyncio.Task[None]] = set()
        self._queue: list[str] = []  # broken findings still to be grilled, in order
        self._current: str | None = None  # the finding the candidate is answering now
        # DEF-14: replays computed in the background, sent once their finding's grill is final.
        self._replays: dict[str, RaceReplay | None] = {}
        self._graded: set[str] = set()
        self._revealed: set[str] = set()

    # --- ModeController ---------------------------------------------------------------------------------

    def allowed_transitions(self) -> Mapping[Phase, set[Phase]]:
        return TRANSITIONS

    async def on_start(self, rt: SessionRuntime) -> None:
        self._pipeline(rt)
        self._spawn(rt, self._opening(rt))

    async def on_resume(self, rt: SessionRuntime) -> None:
        p = self._pipeline(rt)
        await self._restore(rt, p)
        phase = rt.session.phase
        if phase in (Phase.AUDIT, Phase.CHAOS):  # interrupted mid-stage: run it again from the top
            p.state.phase = Phase.SETUP
            await rt.note("info", "session resumed during the audit or attack; running them again")
            self._spawn(rt, self._opening(rt, resumed=True))
        elif phase == Phase.GRILL:
            self._queue = [f for f in p.state.broken if f not in p.state.grill or p.needs_follow_up(f)]
            # The hub resumes a runtime *before* it attaches the reconnecting socket, so ask from a task:
            # it runs once the socket is in place instead of broadcasting the question to nobody.
            self._spawn(rt, self._ask_next(rt))
        elif phase in (Phase.FIX, Phase.VERIFY):
            await self._enter_fix(rt, announce=False)

    async def on_client_message(self, rt: SessionRuntime, msg: ClientMessage) -> bool:
        match msg:
            case DefenseVerify(finding_id=fid, files=files):
                if (
                    rt.session.phase not in (Phase.FIX, Phase.VERIFY, Phase.GRILL)
                    or self._queue
                    or self._current
                ):
                    await self._error(rt, "bad_phase", "Finish the grill before verifying a fix.")
                elif self._lock.locked() or self._attack_pending:
                    await self._error(rt, "busy", "An attack is still running.", retryable=True)
                else:
                    self._attack_pending = True
                    self._spawn(rt, self._verify(rt, fid, files))
                return True
            case DefenseRunChaos(finding_id=fid):
                p = self.pipeline
                run = p.state.baseline.get(fid) if p else None
                if run is None or run.verdict != "error":
                    await self._error(rt, "bad_request", "Only a baseline attack that errored can be re-run.")
                elif self._lock.locked() or self._attack_pending:
                    await self._error(rt, "busy", "An attack is still running.", retryable=True)
                else:
                    self._attack_pending = True
                    self._spawn(rt, self._rerun_baseline(rt, fid))
                return True
        return False  # defense.circle (DEF-9) and anything else: unsupported for now

    async def on_timeline(self, rt: SessionRuntime, event: TimelineEvent) -> None:
        if (
            event.kind == TimelineKind.PHASE
            and PhaseChange.model_validate(event.payload).to_phase == Phase.ENDED
        ):
            # An attack mid-run must not keep writing after the session ended (#22).
            await self._cancel_tasks()
            return
        if event.kind != TimelineKind.TRANSCRIPT or rt.session.phase != Phase.GRILL or self._current is None:
            return
        turn = TranscriptTurn.model_validate(event.payload)
        if turn.speaker == "candidate" and turn.final and turn.text.strip():
            self._spawn(rt, self._grade(rt, self._current, turn.text))

    async def report_extra(self, rt: SessionRuntime) -> DefenseExtra:
        p = self._pipeline(rt)
        if p.state.audit is None:
            await self._restore(rt, p)
        verdict = p.state.verdict or verdict_mod.decide(
            p.state.broken, p.state.verify, p.state.grill, p.state.baseline
        )
        runs = [*p.state.baseline.values(), *p.state.verify.values()]
        return DefenseExtra(
            findings=p.state.audit.findings if p.state.audit else [],
            chaos_runs=runs,
            grill=list(p.state.grill.values()),
            verdict=verdict,
            card_url=None,
        )

    # --- stages (background) ----------------------------------------------------------------------------

    async def _opening(self, rt: SessionRuntime, *, resumed: bool = False) -> None:
        p = self._pipeline(rt)
        async with self._lock:
            try:
                await p.run_audit()
            except AuditFailed as exc:
                await rt.note("error", f"audit failed: {exc}")
                await rt.set_phase(Phase.FAILED, "audit failed")
                return
            await p.run_baselines()
        self._spawn(rt, self._prepare_replays(rt))
        if not p.state.broken:
            await self._finish(rt, "nothing broke under load")
            return
        await p.set_phase(Phase.GRILL, "chaos broke at least one finding")
        self._queue = list(p.state.broken)
        await self._ask_next(rt)

    async def _grade(self, rt: SessionRuntime, fid: str, answer: str) -> None:
        p = self._pipeline(rt)
        async with self._lock:
            if self._current != fid:  # a second message raced the first; that answer was already graded
                return
            turn = await p.answer_grill(fid, answer)
        finding = p.finding(fid)
        if turn.eval.feedback:
            await self._say(rt, turn.eval.feedback, InterventionLevel.INFO)
        if p.needs_follow_up(fid):
            # The eval carries the full finding (explanation, expected points), so it goes out only once
            # the grill for this finding is final; revealing it before the follow-up hands over the answer.
            await self._say(rt, finding.grill.follow_up, InterventionLevel.QUESTION)
            return
        await rt.broadcast(DefenseGrillEval(type="defense.grill.eval", turn=turn, finding=finding))
        self._graded.add(fid)
        await self._reveal_replay(rt, fid)
        self._current = None
        await self._ask_next(rt)

    async def _verify(self, rt: SessionRuntime, fid: str, files: dict[str, str]) -> None:
        async with self._lock:
            self._attack_pending = False
            p = self._pipeline(rt)
            if rt.session.phase not in (Phase.FIX, Phase.VERIFY, Phase.GRILL):
                return  # the session finished while this waited
            try:
                run = await p.verify(fid, files)
            except (LookupError, ValueError) as exc:
                await self._error(rt, "bad_request", str(exc))
                return
        if run.verdict == "held":
            if all(p.state.verify.get(f) and p.state.verify[f].verdict == "held" for f in p.state.broken):
                await self._finish(rt, "every broken finding held under the same attack")
            else:
                await self._say(
                    rt, f"{fid} holds now. Verify the others when you're ready.", InterventionLevel.INFO
                )
        elif p.state.verify_rounds.get(fid, 0) >= MAX_FIX_ROUNDS:
            await self._finish(rt, f"{fid} still broke after {MAX_FIX_ROUNDS} tries")
        else:
            await self._say(rt, f"Still breaking: {run.summary}. Take another look.", InterventionLevel.NUDGE)

    async def _rerun_baseline(self, rt: SessionRuntime, fid: str) -> None:
        async with self._lock:
            self._attack_pending = False
            p = self._pipeline(rt)
            fn = p.state.attacks.get(fid)
            if fn is None:
                await self._error(rt, "bad_request", f"{fid} has no attack to re-run")
                return
            run = await run_attack(
                p.runner,
                p.sample.project,
                p.sample.files,
                p.finding(fid),
                fn,
                p.sink,
                kind="baseline",
                attempt=p.state.baseline[fid].attempt + 1,
                duration_override_s=p.duration_override_s,
            )
            p.state.baseline[fid] = run
        if run.verdict == "broke" and rt.session.phase == Phase.CHAOS:
            await p.set_phase(Phase.GRILL, "a re-run attack broke the finding")
            self._queue = [fid]
            await self._ask_next(rt)

    async def _finish(self, rt: SessionRuntime, reason: str) -> None:
        p = self._pipeline(rt)
        await p.decide()  # → verdict phase, timeline + defense.verdict
        await rt.end(reason)

    # --- helpers --------------------------------------------------------------------------------------------

    async def _ask_next(self, rt: SessionRuntime) -> None:
        p = self._pipeline(rt)
        if not self._queue:
            await self._enter_fix(rt)
            return
        self._current = self._queue.pop(0)
        finding = p.finding(self._current)
        previous = p.state.grill.get(self._current)
        text = (
            finding.grill.follow_up
            if previous
            else grill_question(finding, p.state.baseline[finding.id].summary)
        )
        await self._say(rt, text, InterventionLevel.QUESTION)

    async def _enter_fix(self, rt: SessionRuntime, *, announce: bool = True) -> None:
        p = self._pipeline(rt)
        if rt.session.phase == Phase.GRILL:
            await p.set_phase(Phase.FIX, "grill done")
        await rt.attach(self._fix_context(p))
        if announce:
            await self._say(rt, FIX_PROMPT, InterventionLevel.INFO)

    def _fix_context(self, p: DefensePipeline) -> RubricContext:
        findings = [p.finding(f) for f in p.state.broken]
        fixed = p.sample.fixed_files or {}
        brief = "\n\n".join(
            f"### {f.title}\n{f.explanation}\n\nLoad test: {p.state.baseline[f.id].summary}" for f in findings
        )
        steps = [s.model_copy(update={"id": f"{f.id}-{s.id}"}) for f in findings for s in f.fix_steps]
        reference = "\n".join(fixed[f.file] for f in findings if f.file in fixed) or None
        return RubricContext(
            title="Fix: " + "; ".join(f.title for f in findings),
            brief_md=brief,
            steps=steps,
            edge_cases=[],
            common_mistakes=[],
            wrap_up_questions=[],
            reference_text=reference,
            files=sorted({f.file for f in findings}),
        )

    async def _say(self, rt: SessionRuntime, text: str, level: InterventionLevel) -> None:
        """Interviewer line for the grill. TODO(ENG-6): switch to `interviewer.say(..., fallback=...)`."""
        if looks_like_code(text):
            await rt.note("info", "leak guard replaced a grill message")
            text = SAFE_FEEDBACK
        intervention = Intervention(
            id=new_id(),
            t=rt.now_ms(),
            trigger=InterventionTrigger.GRILL,
            level=level,
            text=text,
            step_id=None,
            speak=rt.session.config.speak_replies,
            suppressed=False,
        )
        await rt.record(TimelineKind.INTERVENTION, intervention)
        await rt.broadcast(InterviewerMessage(type="interviewer.message", intervention=intervention))
        await rt.record(
            TimelineKind.TRANSCRIPT,
            TranscriptTurn(
                turn_id=new_id(),
                speaker="interviewer",
                text=text,
                start_ms=intervention.t,
                end_ms=intervention.t,
                final=True,
                source="text",
            ),
        )

    async def _error(self, rt: SessionRuntime, code: str, message: str, *, retryable: bool = False) -> None:
        await rt.broadcast(ErrorMsg(type="error", code=code, message=message, retryable=retryable))

    def _pipeline(self, rt: SessionRuntime) -> DefensePipeline:
        if self.pipeline is None:
            sample = self.mode.samples[rt.session.project_id or ""]
            # Bound to this session, so its model calls light up its "Under the hood" strip (#39).
            bind = getattr(self.mode.llm, "for_session", None)
            self.pipeline = DefensePipeline(
                sample,
                self.mode.runner,
                bind(rt.session.id) if bind else self.mode.llm,
                HubSink(rt),
                duration_override_s=self.mode.duration_override_s,
                phase_setter=rt.set_phase,
            )
            self.pipeline.state.phase = rt.session.phase
        return self.pipeline

    async def _prepare_replays(self, rt: SessionRuntime) -> None:
        """DEF-14, in the background while the grill runs: one replay per broken race finding."""
        p = self._pipeline(rt)
        for fid in list(p.state.broken):
            self._replays[fid] = await p.prepare_replay(fid)
            await self._reveal_replay(rt, fid)

    async def _reveal_replay(self, rt: SessionRuntime, fid: str) -> None:
        """The replay explains the cause, so it goes out only after the finding's grill is final (§11.11)."""
        replay = self._replays.get(fid)
        if replay is None or fid not in self._graded or fid in self._revealed:
            return
        self._revealed.add(fid)
        await self._pipeline(rt).sink.emit(TimelineKind.REPLAY, replay)

    async def on_close(self, rt: SessionRuntime) -> None:
        """Hub hook (PLAN §9.1): the runtime is closing, so stop every stage still running."""
        await self._cancel_tasks()

    async def _cancel_tasks(self) -> None:
        current = asyncio.current_task()  # the stage that ended the session finishes on its own
        tasks = [t for t in self._tasks if t is not current]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def _spawn(self, rt: SessionRuntime, coro) -> None:
        task = asyncio.create_task(self._guard(rt, coro), name=f"defense-{rt.session.id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _guard(self, rt: SessionRuntime, coro) -> None:
        """Task boundary: a crash becomes an error note and message, never a silent dead session."""
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("defense stage failed in %s", rt.session.id)
            await rt.note("error", f"defense stage failed: {type(exc).__name__}: {exc}")
            await self._error(
                rt, "internal", "Something went wrong in this stage. Try again.", retryable=True
            )

    async def _restore(self, rt: SessionRuntime, p: DefensePipeline) -> None:
        """Rebuild pipeline state from the timeline (a runtime reopened after it expired)."""
        for event in await rt.timeline.read():
            if event.kind == TimelineKind.AUDIT:
                p.state.audit = AuditResult.model_validate(event.payload)
            elif event.kind == TimelineKind.CHAOS_RUN:
                run = ChaosRun.model_validate(event.payload)
                if run.kind == "baseline":
                    p.state.baseline[run.finding_id] = run
                    if run.script:
                        p.state.attacks[run.finding_id] = extract_functions(run.script)
                else:
                    p.state.verify[run.finding_id] = run
                    p.state.verify_rounds[run.finding_id] = run.attempt
            elif event.kind == TimelineKind.GRILL:
                turn = GrillTurn.model_validate(event.payload)
                p.state.grill[turn.finding_id] = turn
        p.state.phase = rt.session.phase
