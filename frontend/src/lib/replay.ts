// Rebuild the candidate's code at any moment of a session, for the report's replay (PLAN §14.3, §14.5).
// Same algorithm as backend/crucible/engine/codestate.py `code_at`; backend/tests/fixtures/replay_case.json
// checks both. Keep this file free of TypeScript-only runtime syntax (enums, namespaces) so Node can run
// its tests with type stripping.
import type { EditorEvent, TimelineEvent } from "@/types/contracts";

const TEXT_KINDS = new Set(["change", "paste", "undo", "redo"]);

/** The code of `file` at session time `t`: the last snapshot at or before `t`, plus the edits after it. */
export function codeAt(timeline: readonly TimelineEvent[], file: string, t: number): string {
  const events = timeline.filter((e) => e.t <= t).sort((a, b) => a.seq - b.seq);
  let code = "";
  let baseSeq = -1;
  for (const e of events) {
    if (e.kind === "snapshot" && e.payload.file === file) {
      code = e.payload.code as string;
      baseSeq = e.seq;
    }
  }
  for (const e of events) {
    if (e.seq <= baseSeq || e.kind !== "editor") continue;
    const edit = e.payload as unknown as EditorEvent;
    if ((edit.file ?? "solution.py") !== file || !TEXT_KINDS.has(edit.kind)) continue;
    code = applyChanges(code, edit);
  }
  return code;
}

/**
 * Apply one editor event's changes. Monaco reports every offset against the text before the event, so
 * changes apply from the highest offset down. Offsets are UTF-16 units, the same as JavaScript strings.
 */
export function applyChanges(code: string, event: EditorEvent): string {
  const changes = [...(event.changes ?? [])].sort((a, b) => b.range_offset - a.range_offset);
  for (const c of changes) {
    const start = Math.min(c.range_offset, code.length);
    const end = Math.min(c.range_offset + c.range_length, code.length);
    code = code.slice(0, start) + c.text + code.slice(end);
  }
  return code;
}
