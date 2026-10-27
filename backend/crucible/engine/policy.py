"""Code decides whether an analysis reaches the candidate (PLAN §9.5).

This is ENG-4's thin version for IC1: only `MISSED_STEP`, the 45 s cooldown, the quiet window after an edit
and no repeats. ENG-5 replaces `decide` with the full rule table, hint ladder and passive-mode logging.
"""

from dataclasses import dataclass, field

from crucible.contracts.coding import Analysis, RubricStep, StepStatus
from crucible.contracts.events import InterventionLevel, InterventionTrigger

COOLDOWN_MS = 45_000  # between unsolicited interventions
QUIET_AFTER_EDIT_MS = 2_500  # never interrupt mid-typing
MIN_CONFIDENCE = 0.7

_NOT_DONE = {StepStatus.NOT_STARTED, StepStatus.SKIPPED}
_UNDER_WAY = {StepStatus.IN_PROGRESS, StepStatus.DONE, StepStatus.INCORRECT}  # incorrect = attempted


@dataclass(frozen=True, slots=True)
class Decision:
    trigger: InterventionTrigger
    level: InterventionLevel
    step_id: str | None
    draft: str | None  # the analyzer's wording, if it matches; the interviewer falls back to the rubric hint


@dataclass(slots=True)
class PolicyState:
    previous: Analysis | None = None
    last_unsolicited_ms: int | None = None
    fired: set[tuple[InterventionTrigger, str | None, InterventionLevel]] = field(default_factory=set)

    def remember(self, decision: Decision, now_ms: int) -> None:
        self.fired.add((decision.trigger, decision.step_id, decision.level))
        self.last_unsolicited_ms = now_ms


def decide(
    analysis: Analysis,
    state: PolicyState,
    *,
    steps: list[RubricStep],
    now_ms: int,
    last_edit_ms: int | None,
) -> Decision | None:
    """MISSED_STEP: a required step is still not done while a later step is under way, in two analyses in a row."""
    if state.previous is None:
        return None
    if state.last_unsolicited_ms is not None and now_ms - state.last_unsolicited_ms < COOLDOWN_MS:
        return None
    if last_edit_ms is not None and now_ms - last_edit_ms < QUIET_AFTER_EDIT_MS:
        return None
    persistent = missed_steps(analysis, steps) & missed_steps(state.previous, steps)
    proposal = analysis.proposal
    for step in sorted((s for s in steps if s.id in persistent), key=lambda s: s.order):
        key = (InterventionTrigger.MISSED_STEP, step.id, InterventionLevel.NUDGE)
        if key in state.fired:
            continue
        matches = (
            proposal is not None
            and proposal.trigger == InterventionTrigger.MISSED_STEP
            and proposal.step_id == step.id
        )
        if matches and proposal.confidence < MIN_CONFIDENCE:
            continue  # the analyzer itself isn't sure: wait
        draft = proposal.text if matches and proposal.level == InterventionLevel.NUDGE else None
        return Decision(InterventionTrigger.MISSED_STEP, InterventionLevel.NUDGE, step.id, draft)
    return None


def missed_steps(analysis: Analysis, steps: list[RubricStep]) -> set[str]:
    """Required steps not done while a step with a higher `order` is in progress, done or attempted."""
    status = {p.step_id: p.status for p in analysis.steps}
    under_way = [s.order for s in steps if status.get(s.id) in _UNDER_WAY]
    if not under_way:
        return set()
    latest = max(under_way)
    return {s.id for s in steps if s.required and s.order < latest and status.get(s.id) in _NOT_DONE}
