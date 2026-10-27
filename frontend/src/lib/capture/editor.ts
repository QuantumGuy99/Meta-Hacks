// Monaco → `editor.events` batches + `editor.snapshot`s for the live interviewer (PLAN §14.3).
// Keep this file free of TypeScript-only runtime syntax (enums, namespaces) so Node can run its tests with
// type stripping.
import type { ClientMessage, EditorEvent } from "@/types/contracts";

/** The parts of Monaco's IStandaloneCodeEditor this uses; a real Monaco editor satisfies it as is. */
export interface CapturableEditor {
  onDidChangeModelContent(listener: (e: ContentChange) => void): Disposable;
  onDidPaste(listener: (e: unknown) => void): Disposable;
  getValue(): string;
  getModel(): { getVersionId(): number } | null;
}

export interface ContentChange {
  changes: readonly { rangeOffset: number; rangeLength: number; text: string }[];
  versionId: number;
  isUndoing: boolean;
  isRedoing: boolean;
  isFlush?: boolean;
}

interface Disposable {
  dispose(): void;
}

export interface CaptureOptions {
  /** `session.started_at` as epoch ms, from `session.state`. Event times are ms since then. */
  startedAtMs: number;
  /** Starting file name; change it with `setFile`. */
  file?: string;
  /** Session ms now. Defaults to a monotonic clock aligned to `startedAtMs`. */
  now?: () => number;
  /** Where visibility and focus events come from. Defaults to `document` and `window`. */
  doc?: EventTarget & { visibilityState: string };
  win?: EventTarget;
}

export interface EditorCapture {
  /** Send any pending events, then a snapshot. Call before `code.run`, `code.submit` and `defense.verify`. */
  snapshot(): void;
  /** Send pending events now. */
  flush(): void;
  /** Switch the file the editor shows (defense tabs): flushes, then snapshots the new file. */
  setFile(file: string): void;
  /** Run a programmatic edit (reset to starter code, load a file) without recording it as typing. */
  programmatic(edit: () => void): void;
  dispose(): void;
}

export const BATCH_MS = 500;
export const SNAPSHOT_EVERY_CHANGES = 20;
export const SNAPSHOT_IDLE_MS = 15_000;

export function attachEditorCapture(
  editor: CapturableEditor,
  send: (msg: ClientMessage) => void,
  opts: CaptureOptions,
): EditorCapture {
  const now = opts.now ?? sessionClock(opts.startedAtMs);
  const doc = opts.doc ?? (typeof document === "undefined" ? undefined : document);
  const win = opts.win ?? (typeof window === "undefined" ? undefined : window);
  let file = opts.file ?? "solution.py";
  let buffer: EditorEvent[] = [];
  let changesSinceSnapshot = 0;
  let lastSnapshotAt = now();
  let pasteFlag = false; // set if onDidPaste fires before its content change
  let suppress = false;

  const version = () => editor.getModel()?.getVersionId() ?? 0;

  const flush = () => {
    if (buffer.length === 0) return;
    send({ type: "editor.events", events: buffer });
    buffer = [];
  };

  const snapshot = () => {
    flush();
    send({
      type: "editor.snapshot",
      snapshot: { t: now(), file, version: version(), code: editor.getValue() },
    });
    changesSinceSnapshot = 0;
    lastSnapshotAt = now();
  };

  const push = (kind: EditorEvent["kind"], extra: Partial<EditorEvent> = {}) => {
    buffer.push({ t: now(), file, version: version(), kind, changes: [], ...extra });
  };

  const onContent = (e: ContentChange) => {
    // A flush (setValue) or a programmatic edit replaces text the candidate didn't type: snapshot it instead
    // (programmatic() takes its own snapshot when the edit is done).
    if (suppress) return;
    if (e.isFlush) {
      snapshot();
      return;
    }
    const changes = e.changes.map((c) => ({
      range_offset: c.rangeOffset,
      range_length: c.rangeLength,
      text: c.text,
    }));
    const kind = e.isUndoing ? "undo" : e.isRedoing ? "redo" : pasteFlag ? "paste" : "change";
    const pasted = kind === "paste" ? changes.reduce((n, c) => n + c.text.length, 0) : null;
    buffer.push({ t: now(), file, version: e.versionId, kind, changes, pasted_chars: pasted });
    pasteFlag = false;
    changesSinceSnapshot += 1;
    if (changesSinceSnapshot >= SNAPSHOT_EVERY_CHANGES) snapshot();
  };

  const onPaste = () => {
    // Monaco fires onDidPaste after the paste's content change, so relabel that change. If a build ever
    // fires it first, the flag labels the next change instead.
    const last = buffer[buffer.length - 1];
    if (last && last.kind === "change" && last.version === version()) {
      last.kind = "paste";
      last.pasted_chars = (last.changes ?? []).reduce((n, c) => n + c.text.length, 0);
    } else {
      pasteFlag = true;
    }
  };

  const onVisibility = () => push(doc?.visibilityState === "hidden" ? "hidden" : "visible");
  const onBlur = () => push("blur");
  const onFocus = () => push("focus");

  const subscriptions = [editor.onDidChangeModelContent(onContent), editor.onDidPaste(onPaste)];
  doc?.addEventListener("visibilitychange", onVisibility);
  win?.addEventListener("blur", onBlur);
  win?.addEventListener("focus", onFocus);

  const timer = setInterval(() => {
    flush();
    if (changesSinceSnapshot > 0 && now() - lastSnapshotAt >= SNAPSHOT_IDLE_MS) snapshot();
  }, BATCH_MS);

  return {
    snapshot,
    flush,
    setFile(next) {
      flush();
      file = next;
      snapshot();
    },
    programmatic(edit) {
      flush();
      suppress = true;
      try {
        edit();
      } finally {
        suppress = false;
      }
      snapshot();
    },
    dispose() {
      clearInterval(timer);
      flush();
      for (const s of subscriptions) s.dispose();
      doc?.removeEventListener("visibilitychange", onVisibility);
      win?.removeEventListener("blur", onBlur);
      win?.removeEventListener("focus", onFocus);
    },
  };
}

/** Ms since `startedAtMs`, from a monotonic clock so system clock changes don't move it. */
function sessionClock(startedAtMs: number): () => number {
  const perfAtStart = performance.now() - (Date.now() - startedAtMs);
  return () => Math.round(performance.now() - perfAtStart);
}
