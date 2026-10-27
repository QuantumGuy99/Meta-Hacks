"""SqliteStore round-trips every contract it stores (needs the contracts from S-1, PR #5)."""

import json
from pathlib import Path

import pytest

pytest.importorskip("crucible.contracts.report", reason="contracts (S-1, #5) not merged yet")

from crucible.contracts.common import Phase, Session
from crucible.contracts.defense import AuditResult, Project
from crucible.contracts.events import TimelineEvent, TimelineKind
from crucible.contracts.report import Report
from crucible.store.repo import SqliteStore

FIXTURES = Path(__file__).parents[1] / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
async def store(tmp_path):
    s = await SqliteStore.open(tmp_path / "crucible.db")
    yield s
    await s.close()


def event(seq: int, kind: TimelineKind = TimelineKind.SYSTEM) -> TimelineEvent:
    return TimelineEvent(seq=seq, t=seq * 100, kind=kind, payload={"level": "info", "message": f"e{seq}"})


async def test_sessions_create_get_update(store):
    s = Session.model_validate(fixture("session.json"))
    await store.create_session(s)
    assert await store.get_session(s.id) == s
    moved = s.model_copy(update={"phase": Phase.ENDED})
    await store.update_session(moved)
    assert (await store.get_session(s.id)).phase == Phase.ENDED
    assert await store.get_session("missing") is None
    with pytest.raises(KeyError):
        await store.update_session(moved.model_copy(update={"id": "missing"}))


async def test_events_in_order_filtered_and_retry_safe(store):
    await store.append_events("s1", [event(1), event(2, TimelineKind.PHASE)])
    await store.append_events("s1", [event(2, TimelineKind.PHASE), event(3)])  # retried batch overlaps
    assert [e.seq for e in await store.read_events("s1")] == [1, 2, 3]
    assert [e.seq for e in await store.read_events("s1", kinds={TimelineKind.PHASE})] == [2]
    assert [e.seq for e in await store.read_events("s1", since_seq=1)] == [2, 3]
    assert await store.read_events("s1", kinds=set()) == []
    assert await store.read_events("other") == []


async def test_reports_projects_audits(store):
    report = Report.model_validate(fixture("report_coding.json"))
    await store.save_report(report)
    assert await store.get_report(report.session_id) == report

    project = Project.model_validate(fixture("project.json"))
    files = {"app/main.py": "print('hi')\n"}
    await store.save_project(project, files)
    assert await store.get_project(project.id) == (project, files)

    audit = AuditResult.model_validate(fixture("audit_result.json"))
    await store.save_audit(project.content_hash, audit)
    assert await store.get_audit(project.content_hash) == audit
    assert await store.get_audit("nope") is None


async def test_data_survives_reopen(tmp_path):
    path = tmp_path / "crucible.db"
    s = await SqliteStore.open(path)
    await s.append_events("s1", [event(1)])
    await s.close()
    s = await SqliteStore.open(path)
    assert [e.seq for e in await s.read_events("s1")] == [1]
    await s.close()
