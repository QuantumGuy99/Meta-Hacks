"""Code decides when the interviewer speaks and how much it helps (PLAN §9.5).

`PolicyState` collects what happened (analyses, runs, pastes, questions, hint requests) and what was already
said. `decide()` turns it and a `Facts` snapshot into at most one `Decision`. Neither does I/O or reads a
clock, so tests drive them with numbers; `engine/live.py` feeds the state and calls `decide()` every tick.
"""

from collections import deque
from dataclasses import dataclass, field, replace

from crucible.contracts.coding import Analysis, RubricStep, StepStatus, SuspectedIssue
from crucible.contracts.common import Phase
from crucible.contracts.events import EditorEvent, InterventionLevel, InterventionTrigger, RunResult
from crucible.engine.codestate import BULK_INSERT_CHARS

# Global guards for unsolicited messages
QUIET_AFTER_EDIT_MS = 2_500  # never interrupt mid-typing
SPEECH_GAP_MS = 2_000  # a partial transcript this recent means the candidate is still talking
HOLD_MAX_MS = 20_000  # a message held for a quiet moment is stale after this
COOLDOWN_MS = 45_000
CAP_WINDOW_MS = 30 * 60_000
CAP_COUNT = 8
# Rule thresholds
MIN_CONFIDENCE = 0.7  # MISSED_STEP waits while the analyzer's own proposal is less sure than this
BUG_MIN_CONFIDENCE = 0.75
BUG_STABLE_MS = 20_000
TIME_MARKS = (0.5, 0.8)
PASTE_MIN_CHARS = 40
PASTE_MIN_LINES = 2
PLAN_MIN_LINES = 3
RUN_IDLE_MS = 30_000
SILENT_AFTER_MS = 120_000
SILENT_EVERY_MS = 5 * 60_000
IDLE_AFTER_MS = 75_000
IDLE_EVERY_MS = 3 * 60_000

LADDER = (
    InterventionLevel.NUDGE,
    InterventionLevel.QUESTION,
    InterventionLevel.HINT,
    InterventionLevel.CONCEPT,
)
LADDER_TRIGGERS = frozenset(
    {InterventionTrigger.HINT_REQUESTED, InterventionTrigger.RUN_FAILED, InterventionTrigger.MISSED_STEP}
)
# Shown in passive mode too. They answer the candidate or tell the time, so the unsolicited guards skip them.
PASSIVE_DELIVERED = frozenset(
    {InterventionTrigger.ASKED, InterventionTrigger.HINT_REQUESTED, InterventionTrigger.TIME_WARNING}
)

_RECURRING = frozenset({InterventionTrigger.SILENT, InterventionTrigger.IDLE})  # limited by their own clocks
_BUG_KINDS = frozenset({"bug", "edge_case"})
_PLAN_PHASES = frozenset({Phase.CLARIFY, Phase.CODING})
_IDLE_PHASES = frozenset({Phase.CODING, Phase.FIX})
_NOT_DONE = {StepStatus.NOT_STARTED, StepStatus.SKIPPED}
_UNDER_WAY = {StepStatus.IN_PROGRESS, StepStatus.DONE, StepStatus.INCORRECT}  # incorrect = attempted
_QUESTION_WORDS = frozenset(
    {"what", "why", "how", "when", "where", "which", "who", "whose", "any", "can", "could", "should"}
    | {"would", "will", "may", "might", "shall", "is", "are", "am", "was", "were", "do", "does", "did"}
)

EvidenceKey = tuple[InterventionTrigger, str | None]
RepeatKey = tuple[InterventionTrigger, str | None, InterventionLevel]


@dataclass(frozen=True, slots=True)
class Decision:
    trigger: InterventionTrigger
    level: InterventionLevel
    step_id: str | None
    draft: (
        str | None
    )  # the analyzer's wording, if it matches; the interviewer falls back to rubric or canned text
    line: int | None = None  # BUG_SUSPECTED: the line to point at
    suppressed: bool = False  # passive mode: logged for the report, never shown


@dataclass(frozen=True, slots=True)
class Facts:
    """The session right now. `live.py` builds one per tick; tests build them by hand."""

    now_ms: int
    phase: Phase
    phase_started_ms: int
    passive: bool
    voice: bool
    time_limit_s: int
    steps: list[RubricStep]
    code: str  # the main file, for BUG_SUSPECTED's line
    lines_written: int  # non-blank lines beyond the starter code
    last_edit_ms: int | None
    last_speech_ms: int | None  # the last final candidate turn, voice or chat
    last_partial_ms: int | None  # the last partial transcript: speech in progress


@dataclass(slots=True)
class _Held:
    key: RepeatKey
    since_ms: int


@dataclass(slots=True)
class PolicyState:
    """One session's policy memory: what happened (`observe_*`) and what the interviewer already did."""

    previous: Analysis | None = None
    latest: Analysis | None = None
    analyses: int = 0
    runs: deque[RunResult] = field(default_factory=lambda: deque(maxlen=2))
    runs_seen: int = 0
    asks: int = 0  # questions waiting for an answer
    hint_requests: deque[str | None] = field(default_factory=deque)
    paste_pending: bool = False
    # What the interviewer did
    ladder: dict[str | None, int] = field(default_factory=dict)  # step → ladder levels shown
    hints_by_level: dict[str, int] = field(default_factory=dict)  # the report's independence score
    last_message_ms: int | None = None  # the cooldown clock: unsolicited messages and answers
    unsolicited_ms: deque[int] = field(default_factory=deque)  # for the 8-per-30-min cap
    fired: set[RepeatKey] = field(default_factory=set)
    acted: dict[EvidenceKey, int] = field(default_factory=dict)  # evidence count at the last fire or drop
    time_marks: int = 0
    paste_said: bool = False
    coded_before_plan_said: bool = False
    # The latest plan the candidate stated, kept after it leaves the analyzer's transcript window.
    plan: str | None = None
    last_silent_ms: int | None = None
    last_idle_ms: int | None = None
    issue_watch: dict[str, tuple[str | None, int]] = field(default_factory=dict)  # issue → (line, since)
    held: _Held | None = None

    def observe_analysis(self, analysis: Analysis) -> None:
        self.previous, self.latest = self.latest, analysis
        self.analyses += 1
        if analysis.stated_plan:
            self.plan = analysis.stated_plan

    def observe_run(self, run: RunResult) -> None:
        self.runs.append(run)
        self.runs_seen += 1

    def observe_edit(self, event: EditorEvent) -> None:
        """Arm PASTE for a paste of ≥ 40 chars or ≥ 2 lines, or a bulk insert (COD-4 logs the flags)."""
        inserted = [change.text for change in event.changes]
        if event.kind == "paste":
            text = "".join(inserted)
            chars = max(len(text), event.pasted_chars or 0)
            lines = sum(1 for line in text.splitlines() if line.strip())
            self.paste_pending |= chars >= PASTE_MIN_CHARS or lines >= PASTE_MIN_LINES
        elif event.kind == "change":
            self.paste_pending |= any(len(text) >= BULK_INSERT_CHARS for text in inserted)

    def ask(self) -> None:
        self.asks += 1

    def request_hint(self, step_id: str | None) -> None:
        self.hint_requests.append(step_id)


def decide(state: PolicyState, facts: Facts) -> Decision | None:
    """At most one message for now (§9.5): rules in table order, the first match wins.

    Answers and time warnings go out at once. Everything else passes the cooldown and the cap, then waits in a
    one-slot hold for a quiet moment. Updates `state` (counters, the ladder, the hold) as it goes.
    """
    answer = _asked(state) or _hint_requested(state, facts) or _time_warning(state, facts)
    if answer is not None:
        return _commit(state, facts, answer)
    _watch_issues(state, facts)
    candidate = _first_unsolicited(state, facts) if _may_interrupt(state, facts.now_ms) else None
    return _hold_or_deliver(state, facts, candidate)


def missed_steps(analysis: Analysis, steps: list[RubricStep]) -> set[str]:
    """Required steps not done while a step with a higher `order` is in progress, done or attempted."""
    status = _statuses(analysis)
    under_way = [s.order for s in steps if status.get(s.id) in _UNDER_WAY]
    if not under_way:
        return set()
    latest = max(under_way)
    return {s.id for s in steps if s.required and s.order < latest and status.get(s.id) in _NOT_DONE}


def is_question(text: str) -> bool:
    """P0 test for a chat line meant for the interviewer: it ends in "?" or opens like a question (§9.7).

    Statements typed in chat ("I'll loop over the readings.") are thinking aloud and get no reply.
    """
    words = text.strip().lower().split()
    return bool(words) and (text.strip().endswith("?") or words[0].strip(",.:;!") in _QUESTION_WORDS)


def written_lines(starter: str, code: str) -> int:
    """Non-blank lines in `code` that the starter code doesn't have (CODED_BEFORE_PLAN)."""
    left: dict[str, int] = {}
    for line in starter.splitlines():
        if line.strip():
            left[line.strip()] = left.get(line.strip(), 0) + 1
    written = 0
    for line in code.splitlines():
        stripped = line.strip()
        if stripped and left.get(stripped, 0) > 0:
            left[stripped] -= 1
        elif stripped:
            written += 1
    return written


# --- guards ----------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Candidate:
    decision: Decision
    subject: str | None  # what the no-repeat guard keys on: the step, issue or plan
    # Recorded on fire or drop, so the rule waits for new evidence (analyses or runs) before it tries again.
    evidence: tuple[EvidenceKey, int] | None = None

    @property
    def key(self) -> RepeatKey:
        return (self.decision.trigger, self.subject, self.decision.level)


def _may_interrupt(state: PolicyState, now_ms: int) -> bool:
    while state.unsolicited_ms and now_ms - state.unsolicited_ms[0] >= CAP_WINDOW_MS:
        state.unsolicited_ms.popleft()
    cooled = state.last_message_ms is None or now_ms - state.last_message_ms >= COOLDOWN_MS
    return cooled and len(state.unsolicited_ms) < CAP_COUNT


def _hold_or_deliver(state: PolicyState, facts: Facts, candidate: _Candidate | None) -> Decision | None:
    """The quiet window's one-slot queue: hold while the candidate types or talks, drop after 20 s."""
    if candidate is None:
        state.held = None
        return None
    now = facts.now_ms
    if state.held is None or state.held.key != candidate.key:
        state.held = _Held(candidate.key, now)
    if now - state.held.since_ms > HOLD_MAX_MS:
        state.held = None
        _mark(state, candidate)  # stale: the rule waits for fresh evidence before it tries again
        if candidate.decision.trigger == InterventionTrigger.PASTE:
            state.paste_pending = False
        return None
    if not _quiet(facts):
        return None
    state.held = None
    return _commit(state, facts, candidate)


def _quiet(facts: Facts) -> bool:
    now = facts.now_ms
    typing = facts.last_edit_ms is not None and now - facts.last_edit_ms < QUIET_AFTER_EDIT_MS
    talking = facts.last_partial_ms is not None and now - facts.last_partial_ms < SPEECH_GAP_MS
    return not (typing or talking)


def _commit(state: PolicyState, facts: Facts, candidate: _Candidate) -> Decision:
    """Record a decision as made: shown, or logged as suppressed in passive mode."""
    decision, now = candidate.decision, facts.now_ms
    trigger = decision.trigger
    suppressed = facts.passive and trigger not in PASSIVE_DELIVERED
    state.fired.add(candidate.key)
    _mark(state, candidate)
    _remember_once(state, trigger, now)
    if trigger != InterventionTrigger.TIME_WARNING:
        state.last_message_ms = now  # answers restart the cooldown too, so no nudge lands right after one
    if trigger not in PASSIVE_DELIVERED:
        state.unsolicited_ms.append(now)
    if trigger in LADDER_TRIGGERS and not suppressed:
        state.ladder[decision.step_id] = state.ladder.get(decision.step_id, 0) + 1
        state.hints_by_level[decision.level.value] = state.hints_by_level.get(decision.level.value, 0) + 1
    return replace(decision, suppressed=suppressed)


def _remember_once(state: PolicyState, trigger: InterventionTrigger, now_ms: int) -> None:
    match trigger:
        case InterventionTrigger.PASTE:
            state.paste_said, state.paste_pending = True, False
        case InterventionTrigger.CODED_BEFORE_PLAN:
            state.coded_before_plan_said = True
        case InterventionTrigger.SILENT:
            state.last_silent_ms = now_ms
        case InterventionTrigger.IDLE:
            state.last_idle_ms = now_ms


def _mark(state: PolicyState, candidate: _Candidate) -> None:
    if candidate.evidence is not None:
        key, count = candidate.evidence
        state.acted[key] = count


def _fresh(state: PolicyState, key: EvidenceKey, count: int, need: int) -> bool:
    """True if `need` pieces of evidence (analyses or runs) arrived since the rule last fired or was dropped."""
    last = state.acted.get(key)
    return last is None or count - last >= need


def _new(state: PolicyState, key: RepeatKey) -> bool:
    return key[0] in _RECURRING or key not in state.fired


# --- rules that answer: ASKED, HINT_REQUESTED, TIME_WARNING ----------------------------------------------------


def _asked(state: PolicyState) -> _Candidate | None:
    if state.asks == 0:
        return None
    state.asks -= 1
    return _Candidate(Decision(InterventionTrigger.ASKED, InterventionLevel.QUESTION, None, None), None)


def _hint_requested(state: PolicyState, facts: Facts) -> _Candidate | None:
    if not state.hint_requests:
        return None
    step_id = _hint_step(state.hint_requests.popleft(), state.latest, facts.steps)
    level = _next_level(state, step_id)
    draft = _draft(state.latest, None, level, step_id)  # any trigger: the step and level are what matter
    return _Candidate(Decision(InterventionTrigger.HINT_REQUESTED, level, step_id, draft), step_id)


def _time_warning(state: PolicyState, facts: Facts) -> _Candidate | None:
    if facts.time_limit_s <= 0:
        return None
    passed = sum(facts.now_ms >= mark * facts.time_limit_s * 1000 for mark in TIME_MARKS)
    if passed <= state.time_marks:
        return None
    state.time_marks = passed  # both marks at once (a resumed session) give one warning
    return _Candidate(Decision(InterventionTrigger.TIME_WARNING, InterventionLevel.INFO, None, None), None)


# --- unsolicited rules, in table order -------------------------------------------------------------------------


def _first_unsolicited(state: PolicyState, facts: Facts) -> _Candidate | None:
    for rule in _UNSOLICITED:
        candidate = rule(state, facts)
        if candidate is not None:
            return candidate
    return None


def _paste(state: PolicyState, facts: Facts) -> _Candidate | None:
    if not state.paste_pending or state.paste_said:
        return None
    return _Candidate(Decision(InterventionTrigger.PASTE, InterventionLevel.INFO, None, None), None)


def _coded_before_plan(state: PolicyState, facts: Facts) -> _Candidate | None:
    latest = state.latest
    if (
        state.coded_before_plan_said
        or not facts.voice
        or facts.phase not in _PLAN_PHASES
        or latest is None
        or latest.stated_plan is not None
        or state.plan is not None  # a plan stated earlier counts, even once the analyzer no longer sees it
        or facts.lines_written < PLAN_MIN_LINES
    ):
        return None
    trigger, level = InterventionTrigger.CODED_BEFORE_PLAN, InterventionLevel.QUESTION
    return _Candidate(Decision(trigger, level, None, _draft(latest, trigger, level)), None)


def _run_failed(state: PolicyState, facts: Facts) -> _Candidate | None:
    """The same visible test failed on 2 runs in a row, or 1 failure then 30 s with no edit or speech."""
    if not state.runs:
        return None
    last = state.runs[-1]
    before = set(_failing(state.runs[0])) if len(state.runs) == 2 else set()
    idle = facts.now_ms - last.t >= RUN_IDLE_MS and _last_activity(facts) <= last.t
    trigger = InterventionTrigger.RUN_FAILED
    for case_id in _failing(last):
        key = (trigger, case_id)
        twice = case_id in before and _fresh(state, key, state.runs_seen, 2)
        if twice or (idle and _fresh(state, key, state.runs_seen, 1)):
            step_id = _run_step(state.latest, facts.steps)
            level = _next_level(state, step_id)
            candidate = _Candidate(
                Decision(trigger, level, step_id, _draft(state.latest, trigger, level, step_id)),
                step_id,
                (key, state.runs_seen),
            )
            return candidate if _new(state, candidate.key) else None
    return None


def _missed_step(state: PolicyState, facts: Facts) -> _Candidate | None:
    """A required step still not done while a later one is under way, in 2 analyses in a row."""
    latest, previous = state.latest, state.previous
    if latest is None or previous is None:
        return None
    trigger, proposal = InterventionTrigger.MISSED_STEP, latest.proposal
    persistent = missed_steps(latest, facts.steps) & missed_steps(previous, facts.steps)
    for step in sorted((s for s in facts.steps if s.id in persistent), key=lambda s: s.order):
        level = _next_level(state, step.id)
        if not _fresh(state, (trigger, step.id), state.analyses, 2) or not _new(
            state, (trigger, step.id, level)
        ):
            continue
        ours = proposal is not None and proposal.trigger == trigger and proposal.step_id == step.id
        if ours and proposal.confidence < MIN_CONFIDENCE:
            continue  # the analyzer itself isn't sure: wait
        decision = Decision(trigger, level, step.id, _draft(latest, trigger, level, step.id))
        return _Candidate(decision, step.id, ((trigger, step.id), state.analyses))
    return None


def _bug_suspected(state: PolicyState, facts: Facts) -> _Candidate | None:
    """A likely bug in 2 analyses in a row whose line hasn't changed for 20 s. Points at the line, never the fix."""
    latest, previous = state.latest, state.previous
    if latest is None or previous is None:
        return None
    trigger, level = InterventionTrigger.BUG_SUSPECTED, InterventionLevel.NUDGE
    earlier = {_issue_key(i) for i in previous.issues if _serious(i)}
    for issue in latest.issues:
        key = _issue_key(issue)
        if not _serious(issue) or key not in earlier:
            continue
        since = state.issue_watch.get(key, (None, facts.now_ms))[1]
        if facts.now_ms - since < BUG_STABLE_MS or not _fresh(state, (trigger, key), state.analyses, 2):
            continue
        if not _new(state, (trigger, key, level)):
            continue
        step_id = latest.proposal.step_id if latest.proposal and latest.proposal.trigger == trigger else None
        decision = Decision(
            trigger, level, step_id, None, line=issue.line
        )  # canned text: drafts may hint the fix
        return _Candidate(decision, key, ((trigger, key), state.analyses))
    return None


def _plan_mismatch(state: PolicyState, facts: Facts) -> _Candidate | None:
    latest, previous = state.latest, state.previous
    stated = (latest.stated_plan if latest else None) or state.plan
    if latest is None or previous is None or stated is None:
        return None
    if latest.plan_matches_code is not False or previous.plan_matches_code is not False:
        return None
    trigger, level = InterventionTrigger.PLAN_MISMATCH, InterventionLevel.QUESTION
    plan = " ".join(stated.lower().split())  # once per plan
    if not _fresh(state, (trigger, None), state.analyses, 2) or not _new(state, (trigger, plan, level)):
        return None
    decision = Decision(trigger, level, None, _draft(latest, trigger, level))
    return _Candidate(decision, plan, ((trigger, None), state.analyses))


def _silent(state: PolicyState, facts: Facts) -> _Candidate | None:
    if not facts.voice or facts.phase != Phase.CODING:
        return None
    since = max(facts.phase_started_ms, facts.last_speech_ms or 0)
    if facts.now_ms - since < SILENT_AFTER_MS or not _every(
        state.last_silent_ms, facts.now_ms, SILENT_EVERY_MS
    ):
        return None
    trigger, level = InterventionTrigger.SILENT, InterventionLevel.NUDGE
    return _Candidate(Decision(trigger, level, None, _draft(state.latest, trigger, level)), None)


def _idle(state: PolicyState, facts: Facts) -> _Candidate | None:
    if facts.phase not in _IDLE_PHASES:
        return None
    since = max(facts.phase_started_ms, _last_activity(facts))
    if facts.now_ms - since < IDLE_AFTER_MS or not _every(state.last_idle_ms, facts.now_ms, IDLE_EVERY_MS):
        return None
    trigger, level = InterventionTrigger.IDLE, InterventionLevel.QUESTION
    return _Candidate(Decision(trigger, level, None, _draft(state.latest, trigger, level)), None)


# TODO(ENG-5): PRAISE ("a step marked tricky becomes done", max 1 per 10 min) needs a `tricky` flag on
# RubricStep, which is a contract change (SG + SS).
_UNSOLICITED = (
    _paste,
    _coded_before_plan,
    _run_failed,
    _missed_step,
    _bug_suspected,
    _plan_mismatch,
    _silent,
    _idle,
)


# --- helpers ---------------------------------------------------------------------------------------------------


def _next_level(state: PolicyState, step_id: str | None) -> InterventionLevel:
    return LADDER[min(state.ladder.get(step_id, 0), len(LADDER) - 1)]


def _draft(
    analysis: Analysis | None,
    trigger: InterventionTrigger | None,
    level: InterventionLevel,
    step_id: str | None = None,
) -> str | None:
    """The analyzer's wording if its proposal is for this trigger (None: any), level and step (None: any)."""
    proposal = analysis.proposal if analysis is not None else None
    if proposal is None or proposal.level != level:
        return None
    if (trigger is not None and proposal.trigger != trigger) or (
        step_id is not None and proposal.step_id != step_id
    ):
        return None
    return proposal.text


def _statuses(analysis: Analysis | None) -> dict[str, StepStatus]:
    return {} if analysis is None else {p.step_id: p.status for p in analysis.steps}


def _hint_step(requested: str | None, analysis: Analysis | None, steps: list[RubricStep]) -> str | None:
    """The requested step, else the analyzer's proposal step, else the first required step not done yet."""
    ids = {s.id for s in steps}
    if requested in ids:
        return requested
    proposal = analysis.proposal if analysis is not None else None
    if proposal is not None and proposal.step_id in ids:
        return proposal.step_id
    status = _statuses(analysis)
    pending = [s for s in steps if s.required and status.get(s.id) != StepStatus.DONE]
    return min(pending, key=lambda s: s.order).id if pending else None


def _run_step(analysis: Analysis | None, steps: list[RubricStep]) -> str | None:
    """The step a failing test is about: the analyzer's RUN_FAILED step, else an incorrect one, else the next."""
    proposal = analysis.proposal if analysis is not None else None
    ids = {s.id for s in steps}
    if (
        proposal is not None
        and proposal.trigger == InterventionTrigger.RUN_FAILED
        and proposal.step_id in ids
    ):
        return proposal.step_id
    status = _statuses(analysis)
    ordered = sorted(steps, key=lambda s: s.order)
    wrong = [s for s in ordered if status.get(s.id) == StepStatus.INCORRECT]
    pending = [s for s in ordered if s.required and status.get(s.id) != StepStatus.DONE]
    return (wrong + pending)[0].id if wrong or pending else None


def _failing(run: RunResult) -> list[str]:
    # Hidden tests never count: a message about them could give their inputs away.
    return [case.id for case in run.cases if case.visible and not case.passed]


def _serious(issue: SuspectedIssue) -> bool:
    return issue.kind in _BUG_KINDS and issue.line is not None and issue.confidence >= BUG_MIN_CONFIDENCE


def _issue_key(issue: SuspectedIssue) -> str:
    return f"{issue.kind}:{issue.mistake_id}" if issue.mistake_id else f"{issue.kind}:line {issue.line}"


def _watch_issues(state: PolicyState, facts: Facts) -> None:
    """Track how long each likely bug's line has stayed the same (BUG_SUSPECTED waits for 20 s)."""
    issues = [i for i in state.latest.issues if _serious(i)] if state.latest is not None else []
    lines = facts.code.splitlines()
    watch: dict[str, tuple[str | None, int]] = {}
    for issue in issues:
        key, line = _issue_key(issue), issue.line or 0
        text = lines[line - 1] if 0 < line <= len(lines) else None
        seen = state.issue_watch.get(key)
        watch[key] = (
            seen if seen is not None and text is not None and seen[0] == text else (text, facts.now_ms)
        )
    state.issue_watch = watch


def _last_activity(facts: Facts) -> int:
    return max(facts.last_edit_ms or 0, facts.last_speech_ms or 0)


def _every(last_ms: int | None, now_ms: int, gap_ms: int) -> bool:
    return last_ms is None or now_ms - last_ms >= gap_ms
