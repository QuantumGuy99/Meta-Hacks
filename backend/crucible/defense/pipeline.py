"""DefensePipeline: the Defense stages with no dependency on the engine or WebSockets.

`defense/controller.py` (DefenseController on SG's ModeController hook) will be a thin adapter that maps
client messages to these methods. Standalone, the dev API and the CLI drive it directly.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from crucible.contracts.common import Phase
from crucible.contracts.defense import (
    AttackFunctions,
    AuditResult,
    ChaosRun,
    Finding,
    GrillTurn,
    Verdict,
)
from crucible.contracts.events import ModelActivity, PhaseChange, TimelineKind
from crucible.defense import audit as audit_mod
from crucible.defense import grill as grill_mod
from crucible.defense import verdict as verdict_mod
from crucible.defense.attack_writer import write_attack
from crucible.defense.chaos import run_attack
from crucible.defense.ports import EventSink, ModelClient, note
from crucible.defense.projects import Sample
from crucible.defense.validator import AttackRejected
from crucible.engine.activity import TASKS
from crucible.engine.timeline import public_audit
from crucible.runner.base import Runner

logger = logging.getLogger(__name__)

PhaseSetter = Callable[[Phase, str], Awaitable[None]]
MAX_CHAOS_FINDINGS = 3
MAX_FIX_ROUNDS = 3  # the first fix + 2 extra rounds (PLAN §11.2)


@dataclass
class DefenseState:
    phase: Phase = Phase.SETUP
    audit: AuditResult | None = None
    attacks: dict[str, AttackFunctions] = field(default_factory=dict)
    baseline: dict[str, ChaosRun] = field(default_factory=dict)
    grill: dict[str, GrillTurn] = field(default_factory=dict)
    verify: dict[str, ChaosRun] = field(default_factory=dict)
    verify_rounds: dict[str, int] = field(default_factory=dict)
    verdict: Verdict | None = None

    @property
    def broken(self) -> list[str]:
        return [fid for fid, r in self.baseline.items() if r.verdict == "broke"]


class DefensePipeline:
    def __init__(
        self,
        sample: Sample,
        runner: Runner,
        llm: ModelClient,
        sink: EventSink,
        *,
        duration_override_s: int | None = None,
        phase_setter: PhaseSetter | None = None,
    ) -> None:
        """`phase_setter`: in a live session the hub owns phases (it validates and records them), so the
        controller passes `rt.set_phase`. Standalone, phase changes are emitted to the sink."""
        self.sample = sample
        self.runner = runner
        self.llm = llm
        self.sink = sink
        self._phase_setter = phase_setter
        self.duration_override_s = duration_override_s
        self.state = DefenseState()

    async def set_phase(self, to: Phase, reason: str) -> None:
        if self.state.phase == to:
            return
        if self._phase_setter is not None:
            await self._phase_setter(to, reason)
        else:
            await self.sink.emit(
                TimelineKind.PHASE, PhaseChange(from_phase=self.state.phase, to_phase=to, reason=reason)
            )
        self.state.phase = to

    def finding(self, finding_id: str) -> Finding:
        if self.state.audit is None:
            raise LookupError("no audit yet")
        for f in self.state.audit.findings:
            if f.id == finding_id:
                return f
        raise LookupError(f"unknown finding {finding_id!r}")

    async def run_audit(self) -> AuditResult:
        await self.set_phase(Phase.AUDIT, "session started")
        cached = audit_mod.is_cached(self.sample)
        result = await audit_mod.run_audit(self.sample, self.llm, self.sink)
        if cached:  # no model call was made, but the strip should still say who read the project
            await self.sink.emit(TimelineKind.MODEL_ACTIVITY, cached_audit_activity())
        self.state.audit = result
        await self.sink.emit(TimelineKind.AUDIT, result, public=public_audit(result))
        return result

    async def run_baselines(self) -> dict[str, ChaosRun]:
        """Attack every queued finding (max 3 with a chaos plan) against the original code."""
        assert self.state.audit is not None
        await self.set_phase(Phase.CHAOS, "audit done")
        queued = [f for f in self.state.audit.findings if f.chaos is not None][:MAX_CHAOS_FINDINGS]
        for f in queued:
            ref = self._reference_for(f)
            try:
                fn = await write_attack(f, self.sample.files, self.llm, self.sink, reference=ref)
            except AttackRejected as exc:
                await note(self.sink, "error", f"No attack for {f.id}: {exc}")
                continue
            self.state.attacks[f.id] = fn
            self.state.baseline[f.id] = await run_attack(
                self.runner,
                self.sample.project,
                self.sample.files,
                f,
                fn,
                self.sink,
                kind="baseline",
                duration_override_s=self.duration_override_s,
            )
        if not self.state.broken:
            await note(self.sink, "warning", "No finding broke under load; nothing to grill.")
        return self.state.baseline

    async def answer_grill(
        self, finding_id: str, answer: str, *, sam_node_id: str | None = None
    ) -> GrillTurn:
        if finding_id not in self.state.broken:
            raise LookupError(f"{finding_id} didn't break, so it isn't grilled")
        if self.state.phase != Phase.GRILL:
            await self.set_phase(Phase.GRILL, "chaos broke at least one finding")
        previous = self.state.grill.get(finding_id)
        if previous is not None and previous.follow_up_asked:
            raise LookupError(f"{finding_id} already had its one follow-up")
        finding = self.finding(finding_id)
        turn = await grill_mod.grade(
            finding,
            self.state.baseline[finding_id].summary,
            answer,
            self.llm,
            self.sink,
            sam_node_id=sam_node_id or (previous and previous.sam_node_id),
            follow_up_asked=previous is not None,
            earlier=previous,
        )
        self.state.grill[finding_id] = turn
        return turn

    def needs_follow_up(self, finding_id: str) -> bool:
        """At most one follow-up, enforced here (PLAN §11.5)."""
        turn = self.state.grill.get(finding_id)
        return turn is not None and turn.eval.needs_follow_up and not turn.follow_up_asked

    async def verify(self, finding_id: str, edited_files: dict[str, str]) -> ChaosRun:
        """Re-run the SAME attack functions against the edited files."""
        if finding_id not in self.state.attacks:
            raise LookupError(f"{finding_id} has no baseline attack")
        rounds = self.state.verify_rounds.get(finding_id, 0)
        if rounds >= MAX_FIX_ROUNDS:
            raise LookupError(f"{finding_id} used all {MAX_FIX_ROUNDS} verify rounds")
        if self.state.phase != Phase.VERIFY:
            await self.set_phase(Phase.VERIFY, f"verify {finding_id}")
        unknown = set(edited_files) - set(self.sample.files)
        if unknown:
            raise ValueError(f"edits to files that aren't in the project: {sorted(unknown)}")
        files = {**self.sample.files, **edited_files}
        run = await run_attack(
            self.runner,
            self.sample.project,
            files,
            self.finding(finding_id),
            self.state.attacks[finding_id],
            self.sink,
            kind="verify",
            attempt=rounds + 1,
            duration_override_s=self.duration_override_s,
        )
        self.state.verify_rounds[finding_id] = rounds + 1
        self.state.verify[finding_id] = run
        if run.verdict != "held":
            await self.set_phase(Phase.FIX, f"verify of {finding_id} didn't hold")
        return run

    async def decide(self) -> Verdict:
        await self.set_phase(Phase.VERDICT, "verify done")
        v = verdict_mod.decide(self.state.broken, self.state.verify, self.state.grill, self.state.baseline)
        self.state.verdict = v
        await self.sink.emit(TimelineKind.VERDICT, v)
        return v

    def _reference_for(self, f: Finding) -> AttackFunctions | None:
        if self.state.audit is None:
            return None
        for ref in self.sample.reference_attacks:  # one per chaos flaw (ticket-drop has two)
            if reference_target(self.state.audit.findings, self.sample.flaws, ref.flaw_id) == f.id:
                return ref.functions
        return None


def cached_audit_activity() -> ModelActivity:
    """Muse Wonder's audit came from the cache: "cached" on the strip (STORY.md). `t` is set by the sink."""
    return ModelActivity(
        call_id=uuid.uuid4().hex[:12],
        t=0,
        model_name="Muse Wonder",
        task=TASKS["audit"],
        status="cached",
        latency_ms=0,
    )


REFERENCE_LINE_SLACK = 5  # a model's line range may start or end a few lines off the flaw's


def reference_target(findings: list[Finding], flaws: list[dict], flaw_id: str | None) -> str | None:
    """The finding a sample's reference attack belongs to. A live audit names its own ids, so match the
    flaw in flaws.json by id, then by file and overlapping lines (#35). Without a match, fall back only when
    it can't be the wrong bug: the one chaos finding, or the one with the flaw's category (#50 review)."""
    chaos = [f for f in findings if f.chaos is not None]
    if not chaos:
        return None
    flaw = (
        next((x for x in flaws if x.get("id") == flaw_id), None) if flaw_id else (flaws[0] if flaws else None)
    )
    if flaw_id and any(f.id == flaw_id for f in chaos):
        return flaw_id
    if flaw is not None:
        for f in chaos:
            if f.file == flaw.get("file") and _overlaps(f, flaw):
                return f.id
        same_category = [f for f in chaos if f.category == flaw.get("category")]
        if len(same_category) == 1:
            return same_category[0].id
    return chaos[0].id if len(chaos) == 1 else None


def _overlaps(f: Finding, flaw: dict) -> bool:
    start, end = flaw.get("line_start", 0), flaw.get("line_end", 0)
    return f.line_start <= end + REFERENCE_LINE_SLACK and start <= f.line_end + REFERENCE_LINE_SLACK


async def run_scripted(
    p: DefensePipeline, answers: dict[str, str] | str, edited_files: dict[str, str] | None
) -> Verdict:
    """Drive every stage with scripted inputs: dev API, CLI and end-to-end tests. The real session gets
    answers and edits from the room instead."""
    await p.run_audit()
    await p.run_baselines()
    for fid in p.state.broken:
        answer = answers if isinstance(answers, str) else answers.get(fid, "")
        await p.answer_grill(fid, answer)
        if edited_files is not None:
            await p.verify(fid, {k: v for k, v in edited_files.items() if p.sample.files.get(k) != v})
    return await p.decide()
