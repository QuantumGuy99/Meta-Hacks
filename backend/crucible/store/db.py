"""SQLite connection and schema. One file (DATABASE_URL), WAL mode, one connection per process."""

from __future__ import annotations

from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id   TEXT PRIMARY KEY,
    data TEXT NOT NULL                -- Session JSON
);
CREATE TABLE IF NOT EXISTS events (
    session_id TEXT    NOT NULL,
    seq        INTEGER NOT NULL,
    t          INTEGER NOT NULL,
    kind       TEXT    NOT NULL,
    payload    TEXT    NOT NULL,       -- JSON, validated by Timeline.append before it gets here
    PRIMARY KEY (session_id, seq)
);
CREATE TABLE IF NOT EXISTS reports (
    session_id TEXT PRIMARY KEY,
    data       TEXT NOT NULL          -- Report JSON
);
CREATE TABLE IF NOT EXISTS projects (
    id    TEXT PRIMARY KEY,
    data  TEXT NOT NULL,              -- Project JSON
    files TEXT NOT NULL               -- {path: content} JSON
);
CREATE TABLE IF NOT EXISTS audits (
    content_hash TEXT PRIMARY KEY,
    data         TEXT NOT NULL        -- AuditResult JSON (server-side only: it holds the answers)
);
"""


async def connect(path: Path | None) -> aiosqlite.Connection:
    """Open the database (None = in-memory, for tests) and make sure the schema exists."""
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(":memory:" if path is None else str(path))
    if path is not None:
        await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")
    await conn.executescript(SCHEMA)
    await conn.commit()
    return conn
