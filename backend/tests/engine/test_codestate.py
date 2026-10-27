"""Tests for engine/codestate.py (PLAN §9.3): edit application, counting, snapshots and replay parity."""

import json
from pathlib import Path

import pytest

from crucible.contracts.events import CodeSnapshot, EditorChange, EditorEvent, TimelineEvent
from crucible.engine.codestate import BULK_INSERT_CHARS, CodeState, apply_changes, code_at

REPLAY_CASE = Path(__file__).resolve().parents[1] / "fixtures" / "replay_case.json"


def edit(kind: str, *changes: tuple[int, int, str], t: int = 1000, version: int = 2, **extra) -> EditorEvent:
    return EditorEvent(
        t=t,
        version=version,
        kind=kind,
        changes=[EditorChange(range_offset=o, range_length=n, text=x) for o, n, x in changes],
        **extra,
    )


def state_with(code: str, file: str = "solution.py") -> CodeState:
    state = CodeState()
    state.apply_snapshot(CodeSnapshot(t=0, file=file, version=1, code=code))
    return state


def test_insert_delete_and_replace() -> None:
    state = state_with("abc")
    state.apply(edit("change", (3, 0, "d")))
    state.apply(edit("change", (0, 1, "")))
    state.apply(edit("change", (1, 1, "X")))
    assert state.code() == "bXd"


def test_multi_cursor_changes_apply_against_the_original_text() -> None:
    state = state_with("a b c")
    state.apply(edit("change", (0, 1, "xx"), (2, 1, "yy"), (4, 1, "zz")))  # listed ascending on purpose
    assert state.code() == "xx yy zz"


def test_typing_counts_as_typed_and_paste_as_pasted() -> None:
    state = state_with("")
    applied = state.apply(edit("change", (0, 0, "abc")))
    assert (applied.typed_chars, applied.pasted_chars) == (3, 0)
    applied = state.apply(edit("paste", (3, 0, "x = 1\n"), pasted_chars=6))
    assert (applied.typed_chars, applied.pasted_chars) == (0, 6)
    assert (state.chars_typed, state.chars_pasted) == (3, 6)


def test_undo_and_redo_count_as_neither_typed_nor_pasted() -> None:
    state = state_with("abc")
    state.apply(edit("undo", (0, 3, "")))
    state.apply(edit("redo", (0, 0, "abc")))
    assert state.code() == "abc"
    assert (state.chars_typed, state.chars_pasted) == (0, 0)


def test_a_long_single_insert_without_paste_is_a_bulk_insert() -> None:
    state = state_with("")
    block = "x" * BULK_INSERT_CHARS
    applied = state.apply(edit("change", (0, 0, block)))
    assert applied.bulk_insert_chars == BULK_INSERT_CHARS
    assert (state.chars_typed, state.chars_pasted) == (0, BULK_INSERT_CHARS)


def test_a_short_insert_is_not_a_bulk_insert() -> None:
    applied = state_with("").apply(edit("change", (0, 0, "x" * (BULK_INSERT_CHARS - 1))))
    assert applied.bulk_insert_chars is None


@pytest.mark.parametrize("kind", ["focus", "blur", "hidden", "visible"])
def test_focus_and_visibility_events_change_nothing(kind: str) -> None:
    state = state_with("abc")
    applied = state.apply(edit(kind))
    assert state.code() == "abc" and applied.typed_chars == 0 and state.last_edit_t is None


def test_offsets_are_utf16_units() -> None:
    state = state_with("a\U0001f642b")  # the emoji is two UTF-16 units
    state.apply(edit("change", (3, 0, "!")))
    assert state.code() == "a\U0001f642!b"


def test_out_of_range_offsets_clamp_and_report_desync() -> None:
    state = state_with("abc")
    applied = state.apply(edit("change", (10, 2, "!")))
    assert applied.desynced and state.code() == "abc!"


def test_matching_snapshot_does_not_diverge() -> None:
    state = state_with("abc")
    assert state.apply_snapshot(CodeSnapshot(t=5, file="solution.py", version=3, code="abc")) is False


def test_disagreeing_snapshot_wins_and_reports_it() -> None:
    state = state_with("abc")
    assert state.apply_snapshot(CodeSnapshot(t=5, file="solution.py", version=3, code="xyz")) is True
    assert state.code() == "xyz" and state.version_by_file["solution.py"] == 3


def test_files_are_tracked_separately() -> None:
    state = state_with("main")
    state.apply(edit("change", (0, 0, "notes"), version=1).model_copy(update={"file": "notes.py"}))
    assert state.code() == "main" and state.code("notes.py") == "notes"


def test_whitespace_only_edits_do_not_count_as_changed_since_analysis() -> None:
    state = state_with("x = 1\n")
    state.mark_analyzed()
    state.apply(edit("change", (5, 0, "   ")))
    assert state.changed_since_analysis() is False
    state.apply(edit("change", (0, 0, "y = 2\n")))
    assert state.changed_since_analysis() is True


def test_diff_since_analysis_shows_new_lines() -> None:
    state = state_with("x = 1\n")
    state.mark_analyzed()
    state.apply(edit("change", (6, 0, "y = 2\n")))
    assert "+y = 2" in state.diff_since_analysis()


def test_apply_changes_sorts_by_offset_descending() -> None:
    code, desynced = apply_changes("0123", edit("change", (1, 1, "a"), (3, 1, "b")))
    assert (code, desynced) == ("0a2b", False)


def test_replay_parity_case() -> None:
    """Same checkpoints as frontend/src/lib/__tests__/replay.test.mjs, from the same fixture."""
    case = json.loads(REPLAY_CASE.read_text())
    timeline = [TimelineEvent.model_validate(e) for e in case["events"]]
    for point in case["checkpoints"]:
        assert code_at(timeline, point["file"], point["t"]) == point["code"], point["note"]


def test_live_state_matches_replay_at_the_end() -> None:
    case = json.loads(REPLAY_CASE.read_text())
    state = CodeState()
    for raw in case["events"]:
        event = TimelineEvent.model_validate(raw)
        if event.kind == "snapshot":
            state.apply_snapshot(CodeSnapshot.model_validate(event.payload))
        else:
            state.apply(EditorEvent.model_validate(event.payload))
    final = max(case["checkpoints"], key=lambda p: p["t"])
    assert state.code() == final["code"]
