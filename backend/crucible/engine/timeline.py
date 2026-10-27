"""The session timeline: every event in order, validated (PLAN §9.2). Reports and replay read only this."""

import logging
from collections import deque
from collections.abc import Callable, Iterable
from typing import Any

from pydantic import BaseModel

from crucible.contracts.coding import Analysis
from crucible.contracts.defense import (
    AuditPublic,
    AuditResult,
    ChaosMetric,
    ChaosRun,
    FindingPublic,
    GrillTurn,
    SamHighlight,
    Verdict,
)
from crucible.contracts.events import (
    CodeSnapshot,
    EditorEvent,
    IntegrityFlag,
    Intervention,
    PhaseChange,
    RunResult,
    SystemNote,
    TimelineEvent,
    TimelineKind,
    TranscriptTurn,
)
from crucible.engine.store import Store

logger = logging.getLogger(__name__)

PAYLOAD_MODELS: dict[TimelineKind, type[BaseModel]] = {
    TimelineKind.PHASE: PhaseChange,
    TimelineKind.EDITOR: EditorEvent,
    TimelineKind.SNAPSHOT: CodeSnapshot,
    TimelineKind.TRANSCRIPT: TranscriptTurn,
    TimelineKind.RUN: RunResult,
    TimelineKind.ANALYSIS: Analysis,
    TimelineKind.INTERVENTION: Intervention,
    TimelineKind.INTEGRITY: IntegrityFlag,
    TimelineKind.AUDIT: AuditResult,
    TimelineKind.CHAOS_METRIC: ChaosMetric,
    TimelineKind.CHAOS_RUN: ChaosRun,
    TimelineKind.GRILL: GrillTurn,
    TimelineKind.SAM_HIGHLIGHT: SamHighlight,
    TimelineKind.VERDICT: Verdict,
    TimelineKind.SYSTEM: SystemNote,
}

TAIL_SIZE = 500  # recent events kept in memory for the analyzer
# Never shown while the session is live: they'd hand the candidate hints or answers.
_HIDDEN_WHILE_LIVE = {TimelineKind.ANALYSIS, TimelineKind.SYSTEM}


class TimelineError(Exception):
    """A payload doesn't match its kind's contract model."""


class Timeline:
    """One session's timeline. `append` buffers; `flush` writes to the store (the runtime calls it every 250 ms)."""

    def __init__(self, session_id: str, store: Store, clock: Callable[[], int], last_seq: int = 0) -> None:
        self.session_id = session_id
        self._store = store
        self._clock = clock
        self._seq = last_seq
        self._pending: list[TimelineEvent] = []
        self._tail: deque[TimelineEvent] = deque(maxlen=TAIL_SIZE)

    def append(
        self, kind: TimelineKind, payload: BaseModel | dict[str, Any], t: int | None = None
    ) -> TimelineEvent:
        """Validate, number and buffer an event. `t` defaults to now (ms since the session started)."""
        model = PAYLOAD_MODELS[kind]
        if isinstance(payload, BaseModel):
            if not isinstance(payload, model):
                raise TimelineError(f"{kind} needs a {model.__name__}, got {type(payload).__name__}")
            validated = payload
        else:
            validated = model.model_validate(payload)
        self._seq += 1
        event = TimelineEvent(
            seq=self._seq,
            t=self._clock() if t is None else t,
            kind=kind,
            payload=validated.model_dump(mode="json"),
        )
        self._pending.append(event)
        self._tail.append(event)
        return event

    def tail(
        self, kinds: Iterable[TimelineKind] | None = None, since_t: int | None = None
    ) -> list[TimelineEvent]:
        wanted = set(kinds) if kinds is not None else None
        return [
            e
            for e in self._tail
            if (wanted is None or e.kind in wanted) and (since_t is None or e.t >= since_t)
        ]

    async def flush(self) -> None:
        if not self._pending:
            return
        batch, self._pending = self._pending, []
        try:
            await self._store.append_events(self.session_id, batch)
        except Exception:
            self._pending = batch + self._pending  # keep them for the next flush
            raise

    async def read(self, kinds: set[TimelineKind] | None = None, since_seq: int = 0) -> list[TimelineEvent]:
        await self.flush()
        return await self._store.read_events(self.session_id, kinds, since_seq)


def public_view(events: Iterable[TimelineEvent], *, live: bool) -> list[TimelineEvent]:
    """What `GET /api/sessions/{id}/timeline` may show (PLAN §8.1).

    Always: hidden test cases lose their inputs and outputs. While the session is live, also: no analyses,
    system notes or suppressed interventions, and audits without explanations, grill specs or fix rubrics.
    """
    shown: list[TimelineEvent] = []
    for event in events:
        if live and event.kind in _HIDDEN_WHILE_LIVE:
            continue
        if live and event.kind == TimelineKind.INTERVENTION and event.payload.get("suppressed"):
            continue
        if event.kind == TimelineKind.RUN:
            event = event.model_copy(
                update={"payload": redact_run(RunResult(**event.payload)).model_dump(mode="json")}
            )
        elif live and event.kind == TimelineKind.AUDIT:
            event = event.model_copy(
                update={"payload": public_audit(AuditResult(**event.payload)).model_dump(mode="json")}
            )
        shown.append(event)
    return shown


def redact_run(result: RunResult) -> RunResult:
    """What the browser may see of a run: hidden cases keep pass/fail and the error class only.

    A submit's stdout and stderr are dropped too, because printing the arguments would reveal hidden inputs.
    """
    cases = [
        c
        if c.visible
        else c.model_copy(
            update={
                "input_repr": None,
                "expected_repr": None,
                "actual_repr": None,
                "error": _error_class(c.error),
            }
        )
        for c in result.cases
    ]
    update: dict[str, Any] = {"cases": cases}
    if result.kind == "submit":
        update |= {"stdout": "", "stderr": ""}
    return result.model_copy(update=update)


def public_audit(audit: AuditResult) -> AuditPublic:
    return AuditPublic(
        summary=audit.summary,
        nodes=audit.nodes,
        edges=audit.edges,
        findings=[
            FindingPublic(**f.model_dump(include=set(FindingPublic.model_fields))) for f in audit.findings
        ],
    )


def _error_class(error: str | None) -> str | None:
    # "AssertionError: expected 3 at index 7" → "AssertionError": the message can quote hidden data.
    return error.split(":", 1)[0].strip() if error else None
