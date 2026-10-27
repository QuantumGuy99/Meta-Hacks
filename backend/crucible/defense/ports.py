"""What Defense needs from the rest of the backend, as small interfaces.

Defense runs standalone today; when SG's engine lands, `models/llm.py` satisfies `ModelClient` and a
Timeline + SessionHub adapter satisfies `EventSink`. No Defense logic changes when that happens.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from pydantic import BaseModel

from crucible.contracts.events import SystemNote, TimelineKind

T = TypeVar("T", bound=BaseModel)


class ModelUnavailable(Exception):
    """Every model in the role's chain failed or none is configured. Callers take their fallback."""


class ModelClient(Protocol):
    async def complete_json(self, role: str, messages: list[dict], schema: type[T], *, timeout_s: float) -> T:
        """Structured output for a model role (PLAN §15.1). Raises ModelUnavailable."""
        ...


class EventSink(Protocol):
    async def emit(self, kind: TimelineKind, payload: BaseModel, *, public: BaseModel | None = None) -> None:
        """Append `payload` to the timeline; send `public` (or `payload` if None) to the browser."""
        ...


@dataclass(slots=True)
class SinkEvent:
    seq: int
    t: int
    kind: TimelineKind
    payload: dict
    public: dict


@dataclass
class MemorySink:
    """Standalone EventSink: keeps the timeline in memory (dev API, CLI, tests)."""

    events: list[SinkEvent] = field(default_factory=list)
    echo: bool = False
    _start: float = field(default_factory=time.monotonic)

    async def emit(self, kind: TimelineKind, payload: BaseModel, *, public: BaseModel | None = None) -> None:
        ev = SinkEvent(
            seq=len(self.events) + 1,
            t=int((time.monotonic() - self._start) * 1000),
            kind=kind,
            payload=payload.model_dump(mode="json"),
            public=(public or payload).model_dump(mode="json"),
        )
        self.events.append(ev)
        if self.echo:
            print(f"[{ev.t / 1000:6.1f}s] {kind.value:<13} {_brief(ev.public)}", flush=True)

    def kinds(self) -> list[str]:
        return [e.kind.value for e in self.events]

    def public_events(self) -> list[dict]:
        return [{"seq": e.seq, "t": e.t, "kind": e.kind.value, "payload": e.public} for e in self.events]


async def note(sink: EventSink, level: str, message: str) -> None:
    """Shorthand for a `system` timeline note (fallbacks, warnings)."""
    await sink.emit(TimelineKind.SYSTEM, SystemNote(level=level, message=message))


def _brief(d: dict) -> str:
    for key in ("message", "summary", "to_phase"):
        if key in d:
            return str(d[key])[:140]
    if "p95_ms" in d:
        return (
            f"rps={d['rps']:<7} p95={d['p95_ms']:<8} errors={d['errors']:<5} "
            f"violations={d['violations']} in_flight={d['in_flight']}"
        )
    if "score" in d:
        return f"score={d['score']} root_cause_hit={d['root_cause_hit']}"
    if "passed" in d:
        return f"passed={d['passed']} reasons={d['reasons']}"
    return str(d)[:140]
