"""Sample loading: one bad sample never stops startup, and fix.patch is applied completely."""

import json
import shutil
from pathlib import Path

import pytest

from crucible.defense import projects
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
    ref = json.loads((bad / "reference_attack.json").read_text())
    del ref["functions"]["rationale"]
    (bad / "reference_attack.json").write_text(json.dumps(ref))
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
