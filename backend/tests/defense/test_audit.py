"""Audit fallbacks and code-side checks; the browser view never carries the answer (PLAN §11.3)."""

import pytest

from crucible.contracts.defense import AuditResult, TopologyNode
from crucible.defense import audit as audit_mod
from crucible.defense.audit import AuditFailed, audit_from_flaws, check_audit, run_audit
from crucible.defense.projects import Sample
from crucible.engine.timeline import public_audit
from tests.defense.fixtures import FakeLLM


@pytest.fixture(autouse=True)
def _clear_cache():
    audit_mod._CACHE.clear()


async def test_falls_back_to_flaws_json_and_logs_it(bank, llm_down, sink):
    result = await run_audit(bank, llm_down, sink)
    assert [f.id for f in result.findings] == ["f1"]
    f = result.findings[0]
    assert f.node_id == "app.main" and f.chaos is not None and f.chaos.concurrency == 200
    assert any(n.flagged for n in result.nodes)
    assert sink.kinds() == ["system"]


async def test_upload_without_ground_truth_fails_loudly(bank, llm_down, sink):
    upload = Sample(project=bank.project, files=bank.files, flaws=[])
    with pytest.raises(AuditFailed):
        await run_audit(upload, llm_down, sink)


async def test_model_result_is_used_and_checked(bank, sink):
    good = audit_mod.audit_from_flaws(bank)
    bogus = good.findings[0].model_copy(update={"node_id": "nope", "line_end": 9999})
    stray = good.findings[0].model_copy(update={"id": "f9", "file": "app/missing.py"})
    model_out = AuditResult(summary="s", nodes=good.nodes, edges=good.edges, findings=[bogus, stray])
    llm = FakeLLM()
    llm.push("audit", model_out)
    result = await run_audit(bank, llm, sink)
    assert [f.id for f in result.findings] == ["f1"]  # finding in an unknown file dropped
    assert result.findings[0].node_id is None  # unknown node id cleared
    assert result.findings[0].line_end == bank.files["app/main.py"].count("\n") + 1
    assert llm.calls == ["audit", "audit"]  # asked again; the retry failed, so the first answer stands


def _audit_with(bank, *files: str) -> AuditResult:
    good = audit_mod.audit_from_flaws(bank)
    base = good.findings[0]
    findings = [base.model_copy(update={"id": f"f{i}", "file": f}) for i, f in enumerate(files)]
    return AuditResult(summary="s", nodes=good.nodes, edges=good.edges, findings=findings)


async def test_audit_asks_again_when_a_finding_names_an_unknown_file(bank, sink):
    llm = FakeLLM()
    llm.push("audit", _audit_with(bank, "hello world"))
    llm.push("audit", _audit_with(bank, "app/main.py"))
    result = await run_audit(bank, llm, sink)
    assert llm.calls == ["audit", "audit"]
    assert [f.file for f in result.findings] == ["app/main.py"]
    assert any("hello world" in e.payload["message"] for e in sink.events)


async def test_audit_does_not_ask_again_when_every_file_exists(bank, sink):
    llm = FakeLLM()
    llm.push("audit", _audit_with(bank, "app/main.py"))
    await run_audit(bank, llm, sink)
    assert llm.calls == ["audit"]


async def test_audit_keeps_the_first_answer_when_the_retry_is_worse(bank, sink):
    llm = FakeLLM()
    llm.push("audit", _audit_with(bank, "app/main.py", "hello world"))
    llm.push("audit", _audit_with(bank, "nope.py"))
    result = await run_audit(bank, llm, sink)
    assert [f.id for f in result.findings] == ["f0"]


def test_unknown_files_lists_each_missing_file_once(bank):
    a = _audit_with(bank, "app/main.py", "x.py", "x.py", "y.py")
    assert audit_mod.unknown_files(a, bank.files) == ["x.py", "y.py"]


def test_public_view_has_no_explanation_grill_or_fix(bank):
    public = public_audit(audit_mod.audit_from_flaws(bank)).model_dump()
    for f in public["findings"]:
        assert set(f) == {"id", "title", "category", "severity", "file", "line_start", "line_end", "node_id"}
    assert "explanation" not in str(public)


def test_findings_capped_and_sorted_by_severity(bank):
    base = audit_mod.audit_from_flaws(bank).findings[0]
    many = [
        # Distinct line ranges: copies of one bug would be merged into a single finding.
        base.model_copy(
            update={"id": f"f{i}", "severity": sev, "line_start": 1 + 8 * i, "line_end": 3 + 8 * i}
        )
        for i, sev in enumerate(["low", "critical", "medium", "high", "low", "critical", "low"])
    ]
    nodes = [TopologyNode(id="app.main", label="main.py", kind="route", file="app/main.py", flagged=False)]
    out = check_audit(AuditResult(summary="s", nodes=nodes, edges=[], findings=many), bank.files)
    assert len(out.findings) == 5
    assert [f.severity for f in out.findings][:2] == ["critical", "critical"]


def test_public_summary_is_built_in_code_not_taken_from_the_model(bank):
    leaky = audit_from_flaws(bank).model_copy(
        update={"summary": "Balances are read before an await and written back without a lock."}
    )
    checked = check_audit(leaky, bank.files)
    assert checked.summary == "1 area of this project needs a closer look under load."


def test_titles_that_name_the_cause_are_replaced(bank):
    result = audit_from_flaws(bank)
    leaky = result.findings[0].model_copy(update={"title": "Race condition in transfer"})
    checked = check_audit(result.model_copy(update={"findings": [leaky]}), bank.files)
    assert checked.findings[0].title == "main.py under load"


def test_area_only_titles_are_kept(bank):
    assert audit_from_flaws(bank).findings[0].title == "Balance transfers under load"
