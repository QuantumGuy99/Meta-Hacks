"""Sample loading: one bad sample never stops startup, and fix.patch is applied completely."""

import json
import shutil
from pathlib import Path

import pytest

from crucible.defense import projects
from crucible.defense.audit import audit_from_flaws
from crucible.defense.projects import ProjectInvalid, apply_patch, load_samples

FIXTURE = Path(__file__).parents[1] / "fixtures" / "apps" / "bank-transfer-min"
PATCH = """--- a/app/main.py
+++ b/app/main.py
@@ -1 +1 @@
-x = 1
+x = 2
--- /dev/null
+++ b/app/lock.py
@@ -0,0 +1 @@
+LOCK = None
"""


def _copy_sample(root: Path, name: str) -> Path:
    d = root / name
    shutil.copytree(FIXTURE, d, ignore=shutil.ignore_patterns("fixed", "__pycache__"))
    return d


def test_a_malformed_reference_attack_skips_only_that_sample(tmp_path):
    _copy_sample(tmp_path, "good")
    bad = _copy_sample(tmp_path, "bad")
    ref = json.loads((bad / "reference_attack.json").read_text(encoding="utf-8"))
    del ref["functions"]["rationale"]
    (bad / "reference_attack.json").write_text(json.dumps(ref), encoding="utf-8")
    assert set(load_samples(tmp_path)) == {"good"}


@pytest.mark.skipif(shutil.which("patch") is None, reason="needs GNU patch")
def test_patch_reads_back_files_it_creates():
    out = apply_patch({"app/main.py": "x = 1\n"}, PATCH)
    assert out == {"app/main.py": "x = 2\n", "app/lock.py": "LOCK = None\n"}


def test_missing_patch_program_is_a_clear_project_error(monkeypatch):
    def no_patch(*args, **kwargs):
        raise FileNotFoundError("patch")

    monkeypatch.setattr(projects.subprocess, "run", no_patch)
    with pytest.raises(ProjectInvalid, match="`patch` program"):
        apply_patch({"app/main.py": "x = 1\n"}, PATCH)


def _two_flaw_sample(root: Path) -> Path:
    """The fixture app with a second flaw, and reference_attack.json as a list (one attack per flaw)."""
    d = _copy_sample(root, "two")
    flaws = json.loads((d / "flaws.json").read_text(encoding="utf-8"))
    # A different category, like ticket-drop's O(n²) loop: a same-category overlap would be merged as one bug.
    flaws.append(
        {**flaws[0], "id": "f2", "category": "complexity", "chaos": {"concurrency": 40, "duration_s": 5}}
    )
    (d / "flaws.json").write_text(json.dumps(flaws), encoding="utf-8")
    ref = json.loads((d / "reference_attack.json").read_text(encoding="utf-8"))
    second = {**ref, "flaw_id": "f2", "concurrency": 50, "duration_s": 7}
    (d / "reference_attack.json").write_text(json.dumps([{**ref, "flaw_id": "f1"}, second]), encoding="utf-8")
    return d


def test_a_list_of_reference_attacks_gives_each_flaw_its_own(tmp_path):
    _two_flaw_sample(tmp_path)
    sample = load_samples(tmp_path)["two"]
    assert [r.flaw_id for r in sample.reference_attacks] == ["f1", "f2"]
    assert sample.reference_for("f2", "f1").concurrency == 50
    assert sample.reference_for("f3", "f1") is None
    chaos = {f.id: f.chaos for f in audit_from_flaws(sample).findings}
    assert (chaos["f2"].concurrency, chaos["f2"].duration_s) == (50, 7)


def test_an_attack_without_a_flaw_id_belongs_to_the_first_chaos_finding_only(tmp_path):
    d = _two_flaw_sample(tmp_path)
    ref = json.loads((d / "reference_attack.json").read_text(encoding="utf-8"))[0]
    del ref["flaw_id"]
    (d / "reference_attack.json").write_text(json.dumps(ref), encoding="utf-8")
    sample = load_samples(tmp_path)["two"]
    assert sample.reference_for("f1", "f1") is sample.reference_attack
    assert sample.reference_for("f2", "f1") is None
    chaos = {f.id: f.chaos for f in audit_from_flaws(sample).findings}
    assert (chaos["f2"].concurrency, chaos["f2"].duration_s) == (40, 5)  # its own plan, not f1's attack


def test_two_attacks_for_one_flaw_skip_the_sample(tmp_path):
    d = _copy_sample(tmp_path, "dup")
    ref = json.loads((d / "reference_attack.json").read_text(encoding="utf-8"))
    (d / "reference_attack.json").write_text(json.dumps([ref, ref]), encoding="utf-8")
    assert load_samples(tmp_path) == {}
