"""What the engine needs from storage, plus an in-memory stand-in until `crucible.store` lands (S-0).

The method names match the store interface in plan/shreyas-defense-and-runner.md, so his `store/repo.py`
can replace `MemoryStore` without engine changes.
"""

from typing import Protocol

from crucible.contracts.common import Session
from crucible.contracts.events import TimelineEvent, TimelineKind


class Store(Protocol):
    async def create_session(self, session: Session) -> None: ...
    async def get_session(self, session_id: str) -> Session | None: ...
    async def update_session(self, session: Session) -> None: ...
    async def append_events(self, session_id: str, events: list[TimelineEvent]) -> None: ...
    async def read_events(
        self, session_id: str, kinds: set[TimelineKind] | None = None, since_seq: int = 0
    ) -> list[TimelineEvent]: ...


class MemoryStore:
    """Dev and test stand-in. Everything is lost when the process exits."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._events: dict[str, list[TimelineEvent]] = {}

    async def create_session(self, session: Session) -> None:
        self._sessions[session.id] = session.model_copy(deep=True)
        self._events.setdefault(session.id, [])

    async def get_session(self, session_id: str) -> Session | None:
        session = self._sessions.get(session_id)
        return session.model_copy(deep=True) if session else None

    async def update_session(self, session: Session) -> None:
        self._sessions[session.id] = session.model_copy(deep=True)

    async def append_events(self, session_id: str, events: list[TimelineEvent]) -> None:
        self._events.setdefault(session_id, []).extend(events)

    async def read_events(
        self, session_id: str, kinds: set[TimelineKind] | None = None, since_seq: int = 0
    ) -> list[TimelineEvent]:
        return [
            e
            for e in self._events.get(session_id, [])
            if e.seq > since_seq and (kinds is None or e.kind in kinds)
        ]
