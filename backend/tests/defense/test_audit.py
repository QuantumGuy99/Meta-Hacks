"""Audit fallbacks and code-side checks; the browser view never carries the answer (PLAN §11.3)."""

import pytest

from crucible.contracts.defense import AuditResult, TopologyNode
from crucible.defense import audit as audit_mod
from crucible.defense.audit import AuditFailed, check_audit, run_audit
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


def test_public_view_has_no_explanation_grill_or_fix(bank):
    public = public_audit(audit_mod.audit_from_flaws(bank)).model_dump()
    for f in public["findings"]:
        assert set(f) == {"id", "title", "category", "severity", "file", "line_start", "line_end", "node_id"}
    assert "explanation" not in str(public)


def test_findings_capped_and_sorted_by_severity(bank):
    base = audit_mod.audit_from_flaws(bank).findings[0]
    many = [
        base.model_copy(update={"id": f"f{i}", "severity": sev})
        for i, sev in enumerate(["low", "critical", "medium", "high", "low", "critical", "low"])
    ]
    nodes = [TopologyNode(id="app.main", label="main.py", kind="route", file="app/main.py", flagged=False)]
    out = check_audit(AuditResult(summary="s", nodes=nodes, edges=[], findings=many), bank.files)
    assert len(out.findings) == 5
    assert [f.severity for f in out.findings][:2] == ["critical", "critical"]
