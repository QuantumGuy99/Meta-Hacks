"""SqliteStore: the engine's `Store` protocol (engine/store.py) plus reports, projects and the audit cache.

Interface from plan/shreyas-defense-and-runner.md ("Store interface"). Models go in and out as contract
objects; the database only ever sees their JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from crucible.contracts.common import Session
from crucible.contracts.defense import AuditResult, Project
from crucible.contracts.events import TimelineEvent, TimelineKind
from crucible.contracts.report import Report
from crucible.store.db import connect


class SqliteStore:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._db = conn

    @classmethod
    async def open(cls, path: Path | None) -> SqliteStore:
        return cls(await connect(path))

    async def close(self) -> None:
        await self._db.close()

    # --- sessions -------------------------------------------------------------------------------------

    async def create_session(self, session: Session) -> None:
        await self._db.execute(
            "INSERT INTO sessions (id, data) VALUES (?, ?)", (session.id, session.model_dump_json())
        )
        await self._db.commit()

    async def get_session(self, session_id: str) -> Session | None:
        row = await self._one("SELECT data FROM sessions WHERE id = ?", session_id)
        return Session.model_validate_json(row[0]) if row else None

    async def update_session(self, session: Session) -> None:
        cur = await self._db.execute(
            "UPDATE sessions SET data = ? WHERE id = ?", (session.model_dump_json(), session.id)
        )
        if cur.rowcount == 0:
            raise KeyError(f"unknown session {session.id!r}")
        await self._db.commit()

    # --- timeline ---------------------------------------------------------------------------------------

    async def append_events(self, session_id: str, events: list[TimelineEvent]) -> None:
        """One transaction per batch. A retried batch is harmless: (session_id, seq) already present is
        skipped, never duplicated."""
        await self._db.executemany(
            "INSERT OR IGNORE INTO events (session_id, seq, t, kind, payload) VALUES (?, ?, ?, ?, ?)",
            [(session_id, e.seq, e.t, e.kind.value, json.dumps(e.payload)) for e in events],
        )
        await self._db.commit()

    async def read_events(
        self, session_id: str, kinds: set[TimelineKind] | None = None, since_seq: int = 0
    ) -> list[TimelineEvent]:
        sql = "SELECT seq, t, kind, payload FROM events WHERE session_id = ? AND seq > ?"
        args: list[object] = [session_id, since_seq]
        if kinds is not None:
            if not kinds:
                return []
            sql += f" AND kind IN ({', '.join('?' * len(kinds))})"
            args += [k.value for k in kinds]
        sql += " ORDER BY seq"
        async with self._db.execute(sql, args) as cur:
            rows = await cur.fetchall()
        return [
            TimelineEvent(seq=seq, t=t, kind=TimelineKind(kind), payload=json.loads(payload))
            for seq, t, kind, payload in rows
        ]

    # --- reports, projects, audits ------------------------------------------------------------------

    async def save_report(self, report: Report) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO reports (session_id, data) VALUES (?, ?)",
            (report.session_id, report.model_dump_json()),
        )
        await self._db.commit()

    async def get_report(self, session_id: str) -> Report | None:
        row = await self._one("SELECT data FROM reports WHERE session_id = ?", session_id)
        return Report.model_validate_json(row[0]) if row else None

    async def save_project(self, project: Project, files: dict[str, str]) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO projects (id, data, files) VALUES (?, ?, ?)",
            (project.id, project.model_dump_json(), json.dumps(files)),
        )
        await self._db.commit()

    async def get_project(self, project_id: str) -> tuple[Project, dict[str, str]] | None:
        row = await self._one("SELECT data, files FROM projects WHERE id = ?", project_id)
        return (Project.model_validate_json(row[0]), json.loads(row[1])) if row else None

    async def get_audit(self, content_hash: str) -> AuditResult | None:
        row = await self._one("SELECT data FROM audits WHERE content_hash = ?", content_hash)
        return AuditResult.model_validate_json(row[0]) if row else None

    async def save_audit(self, content_hash: str, audit: AuditResult) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO audits (content_hash, data) VALUES (?, ?)",
            (content_hash, audit.model_dump_json()),
        )
        await self._db.commit()

    async def _one(self, sql: str, *args: object):
        async with self._db.execute(sql, args) as cur:
            return await cur.fetchone()
