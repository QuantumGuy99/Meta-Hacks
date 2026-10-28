"""Integrity notes for coding sessions: pastes, bulk inserts and tab switches (PLAN §10.4, COD-4).

They are facts for the report, never accusations: the wording says what happened and when, nothing more.
"""

from dataclasses import dataclass

from crucible.contracts.events import EditorEvent, IntegrityFlag
from crucible.engine.codestate import BULK_INSERT_CHARS
from crucible.engine.ids import new_id

PASTE_MIN_CHARS = 40
PASTE_MIN_LINES = 2
TAB_HIDDEN_MIN_MS = 10_000


@dataclass(slots=True)
class IntegrityDetector:
    """Turns editor events into `IntegrityFlag`s. Pure apart from its own state (when the tab was hidden)."""

    hidden_since_ms: int | None = None

    def observe(self, event: EditorEvent) -> IntegrityFlag | None:
        if event.kind == "paste":
            text = "".join(c.text for c in event.changes)
            chars = event.pasted_chars if event.pasted_chars is not None else len(text)
            lines = len(text.splitlines())
            if chars >= PASTE_MIN_CHARS or lines >= PASTE_MIN_LINES:
                what = f"{lines} lines" if lines >= PASTE_MIN_LINES else f"{chars} characters"
                return _flag(event.t, "paste", f"pasted {what} at {clock(event.t)}", chars=chars)
        elif event.kind == "change":
            longest = max((len(c.text) for c in event.changes), default=0)
            if longest >= BULK_INSERT_CHARS:
                detail = f"{longest} characters appeared at once at {clock(event.t)}"
                return _flag(event.t, "bulk_insert", detail, chars=longest)
        elif event.kind == "hidden":
            if self.hidden_since_ms is None:
                self.hidden_since_ms = event.t
        elif event.kind == "visible" and self.hidden_since_ms is not None:
            started, self.hidden_since_ms = self.hidden_since_ms, None
            away = event.t - started
            if away >= TAB_HIDDEN_MIN_MS:
                detail = f"switched away for {round(away / 1000)} s at {clock(started)}"
                return _flag(started, "tab_hidden", detail, duration_ms=away)
        return None


def clock(ms: int) -> str:
    seconds = max(0, ms) // 1000
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _flag(
    t: int, kind: str, detail: str, *, chars: int | None = None, duration_ms: int | None = None
) -> IntegrityFlag:
    return IntegrityFlag(id=new_id(), t=t, kind=kind, detail=detail, chars=chars, duration_ms=duration_ms)
