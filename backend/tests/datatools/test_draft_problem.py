"""draft_problem: the model's reply is checked before anything is written, and drafts never overwrite."""

import json

import pytest

from crucible.coding.problems import DEFAULT_ROOT
from crucible.datatools.draft_problem import DraftInvalid, parse_draft, write_draft

GOLD = DEFAULT_ROOT / "room-bookings"


def _reply(**changes) -> str:
    problem = json.loads((GOLD / "problem.json").read_text(encoding="utf-8"))
    problem["slug"] = "harbor-slots"
    body = {
        "problem": problem,
        "statement_md": "# Harbor Slots\n",
        "reference_py": (GOLD / "reference.py").read_text(encoding="utf-8"),
        "brute_py": (GOLD / "brute.py").read_text(encoding="utf-8"),
        "gen_py": (GOLD / "gen.py").read_text(encoding="utf-8"),
        **changes,
    }
    return "```json\n" + json.dumps(body) + "\n```"


def test_a_good_reply_becomes_the_problem_files(tmp_path):
    slug, files = parse_draft(_reply())
    assert slug == "harbor-slots"
    assert set(files) == {"problem.json", "statement.md", "reference.py", "brute.py", "gen.py"}
    folder = write_draft(slug, files, root=tmp_path / "_drafts")
    assert (folder / "gen.py").read_text(encoding="utf-8") == (GOLD / "gen.py").read_text(encoding="utf-8")


def test_a_path_in_the_slug_is_refused():
    problem = json.loads((GOLD / "problem.json").read_text(encoding="utf-8")) | {"slug": "../../evil"}
    with pytest.raises(DraftInvalid, match="slug"):
        parse_draft(_reply(problem=problem))


def test_a_reply_missing_a_file_is_refused():
    with pytest.raises(DraftInvalid, match="brute_py"):
        parse_draft(_reply(brute_py=None))


def test_a_draft_never_overwrites(tmp_path):
    slug, files = parse_draft(_reply())
    write_draft(slug, files, root=tmp_path / "_drafts")
    with pytest.raises(DraftInvalid, match="already exists"):
        write_draft(slug, files, root=tmp_path / "_drafts")
