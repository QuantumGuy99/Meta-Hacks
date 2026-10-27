"""Rebuild the candidate's code from the edit stream (PLAN §9.3). frontend/src/lib/replay.ts mirrors `code_at`."""

import difflib
from collections.abc import Iterable
from dataclasses import dataclass, field

from crucible.contracts.events import CodeSnapshot, EditorEvent, TimelineEvent, TimelineKind

BULK_INSERT_CHARS = 80  # one change this long without a paste event counts as a bulk insert (§10.4)
TEXT_KINDS = frozenset({"change", "paste", "undo", "redo"})


@dataclass(slots=True)
class Applied:
    """What one editor event did. The caller turns these into integrity flags and system notes."""

    typed_chars: int = 0
    pasted_chars: int = 0
    bulk_insert_chars: int | None = None  # size of the largest bulk insert, if any
    desynced: bool = False  # an offset fell outside the reconstructed text; the next snapshot repairs it


@dataclass(slots=True)
class CodeState:
    """Per-session code, rebuilt from `EditorEvent`s and reconciled by `CodeSnapshot`s."""

    code_by_file: dict[str, str] = field(default_factory=dict)
    version_by_file: dict[str, int] = field(default_factory=dict)
    code_at_last_analysis: dict[str, str] = field(default_factory=dict)
    last_edit_t: int | None = None
    chars_typed: int = 0
    chars_pasted: int = 0  # pastes plus bulk inserts: text the candidate didn't type

    def apply(self, event: EditorEvent) -> Applied:
        """Apply one event. Focus, blur and visibility events change no code."""
        if event.kind not in TEXT_KINDS:
            return Applied()
        code, desynced = apply_changes(self.code_by_file.get(event.file, ""), event)
        self.code_by_file[event.file] = code
        self.version_by_file[event.file] = event.version
        self.last_edit_t = event.t
        applied = _count(event)
        applied.desynced = desynced
        self.chars_typed += applied.typed_chars
        self.chars_pasted += applied.pasted_chars
        return applied

    def apply_snapshot(self, snapshot: CodeSnapshot) -> bool:
        """Trust the snapshot. Returns True if it disagreed with the reconstruction (log a system note)."""
        diverged = self.code_by_file.get(snapshot.file, "") != snapshot.code
        self.code_by_file[snapshot.file] = snapshot.code
        self.version_by_file[snapshot.file] = snapshot.version
        return diverged

    def code(self, file: str = "solution.py") -> str:
        return self.code_by_file.get(file, "")

    def changed_since_analysis(self) -> bool:
        """True if any file changed beyond whitespace since `mark_analyzed()` (analyzer trigger, §9.4)."""
        files = self.code_by_file.keys() | self.code_at_last_analysis.keys()
        return any(
            _squash(self.code_by_file.get(f, "")) != _squash(self.code_at_last_analysis.get(f, ""))
            for f in files
        )

    def diff_since_analysis(self, file: str = "solution.py") -> str:
        """Unified diff of `file` since the last analysis, for the analyzer prompt."""
        before = self.code_at_last_analysis.get(file, "").splitlines(keepends=True)
        after = self.code_by_file.get(file, "").splitlines(keepends=True)
        return "".join(difflib.unified_diff(before, after, f"{file} (last analysis)", f"{file} (now)"))

    def mark_analyzed(self) -> None:
        self.code_at_last_analysis = dict(self.code_by_file)


def apply_changes(code: str, event: EditorEvent) -> tuple[str, bool]:
    """Apply an event's changes to `code`. Returns (new code, desynced).

    Monaco reports every change's offset against the text *before* the event, so changes apply from the
    highest offset down. Offsets are UTF-16 code units (JavaScript strings), converted here.
    """
    desynced = False
    for change in sorted(event.changes, key=lambda c: c.range_offset, reverse=True):
        start = _utf16_to_index(code, change.range_offset)
        end = _utf16_to_index(code, change.range_offset + change.range_length)
        if start is None or end is None:
            desynced = True
            start = len(code) if start is None else start
            end = len(code) if end is None else end
        code = code[:start] + change.text + code[end:]
    return code, desynced


def code_at(timeline: Iterable[TimelineEvent], file: str, t: int) -> str:
    """The code of `file` at session time `t`: the last snapshot at or before `t`, plus the edits after it.

    Same algorithm as `codeAt` in frontend/src/lib/replay.ts; backend/tests/fixtures/replay_case.json checks both.
    """
    events = sorted((e for e in timeline if e.t <= t), key=lambda e: e.seq)
    base, base_seq = "", -1
    for event in events:
        if event.kind == TimelineKind.SNAPSHOT and event.payload.get("file") == file:
            base, base_seq = event.payload["code"], event.seq
    code = base
    for event in events:
        if event.seq <= base_seq or event.kind != TimelineKind.EDITOR:
            continue
        if event.payload.get("file", "solution.py") != file:
            continue
        editor_event = EditorEvent.model_validate(event.payload)
        if editor_event.kind in TEXT_KINDS:
            code, _ = apply_changes(code, editor_event)
    return code


def _count(event: EditorEvent) -> Applied:
    # Undo and redo restore earlier text, so they count as neither typed nor pasted.
    inserted = [len(c.text) for c in event.changes]
    if event.kind == "paste":
        return Applied(pasted_chars=sum(inserted))
    if event.kind != "change":
        return Applied()
    bulk = [n for n in inserted if n >= BULK_INSERT_CHARS]
    if bulk:
        return Applied(
            typed_chars=sum(inserted) - sum(bulk), pasted_chars=sum(bulk), bulk_insert_chars=max(bulk)
        )
    return Applied(typed_chars=sum(inserted))


def _utf16_to_index(text: str, offset: int) -> int | None:
    """Python string index for a UTF-16 offset, or None if it's past the end of `text`."""
    if offset < 0:
        return None
    if text.isascii():
        return offset if offset <= len(text) else None
    units = 0
    for index, char in enumerate(text):
        if units >= offset:
            return index if units == offset else None  # offset points inside a surrogate pair
        units += 2 if ord(char) > 0xFFFF else 1
    return len(text) if units == offset else None


def _squash(code: str) -> str:
    return "".join(code.split())
