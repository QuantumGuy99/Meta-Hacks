// Tests for lib/capture/editor.ts (PLAN §14.3) against a fake Monaco editor.
// Run: node --experimental-strip-types --test "frontend/src/lib/**/*.test.mjs"
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  attachEditorCapture,
  BATCH_MS,
  SNAPSHOT_EVERY_CHANGES,
  SNAPSHOT_IDLE_MS,
} from "../capture/editor.ts";

class FakeEditor {
  value = "";
  versionId = 1;
  contentListeners = [];
  pasteListeners = [];

  onDidChangeModelContent(listener) {
    this.contentListeners.push(listener);
    return { dispose: () => (this.contentListeners = this.contentListeners.filter((l) => l !== listener)) };
  }

  onDidPaste(listener) {
    this.pasteListeners.push(listener);
    return { dispose: () => (this.pasteListeners = this.pasteListeners.filter((l) => l !== listener)) };
  }

  getValue() {
    return this.value;
  }

  getModel() {
    return { getVersionId: () => this.versionId };
  }

  edit(offset, length, text, flags = {}) {
    this.value = this.value.slice(0, offset) + text + this.value.slice(offset + length);
    this.versionId += 1;
    const event = {
      changes: [{ rangeOffset: offset, rangeLength: length, text }],
      versionId: this.versionId,
      isUndoing: Boolean(flags.undo),
      isRedoing: Boolean(flags.redo),
      isFlush: Boolean(flags.flush),
    };
    for (const listener of this.contentListeners) listener(event);
  }

  // Monaco fires onDidPaste after the paste's content change.
  paste(offset, text) {
    this.edit(offset, 0, text);
    for (const listener of this.pasteListeners) listener({});
  }
}

class FakeDoc extends EventTarget {
  visibilityState = "visible";
}

// `baseline` is what attaching sent; `sent` starts empty, so each test sees only what it caused.
function setup(t, { value = "", file, clockMs = 0 } = {}) {
  t.mock.timers.enable({ apis: ["setInterval"] });
  const clock = { ms: clockMs };
  const sent = [];
  const editor = new FakeEditor();
  editor.value = value;
  const doc = new FakeDoc();
  const win = new EventTarget();
  const capture = attachEditorCapture(editor, (msg) => sent.push(msg), {
    startedAtMs: 0,
    file,
    now: () => clock.ms,
    doc,
    win,
  });
  t.after(() => capture.dispose());
  const baseline = sent.splice(0);
  const tick = (ms) => {
    clock.ms += ms;
    t.mock.timers.tick(ms);
  };
  return { capture, clock, sent, baseline, editor, doc, win, tick };
}

const events = (sent) => sent.filter((m) => m.type === "editor.events").flatMap((m) => m.events);
const snapshots = (sent) => sent.filter((m) => m.type === "editor.snapshot").map((m) => m.snapshot);

test("attaching sends one snapshot of the code the editor opened with", (t) => {
  const { baseline } = setup(t, { value: "def two_sum(nums, target):\n    pass\n", clockMs: 1200 });
  assert.deepEqual(baseline, [
    {
      type: "editor.snapshot",
      snapshot: { t: 1200, file: "solution.py", version: 1, code: "def two_sum(nums, target):\n    pass\n" },
    },
  ]);
});

test("the baseline snapshot names the starting file, even when the editor is empty", (t) => {
  const { baseline } = setup(t, { file: "app/main.py" });
  assert.deepEqual(snapshots(baseline), [{ t: 0, file: "app/main.py", version: 1, code: "" }]);
});

test("edits after the baseline replay onto it", (t) => {
  const { baseline, sent, editor, tick } = setup(t, { value: "def f():\n    pass\n" });
  editor.edit(13, 4, "return 1");
  tick(BATCH_MS);
  const [base] = snapshots(baseline);
  const [event] = events(sent);
  const { range_offset: at, range_length: n, text } = event.changes[0];
  assert.equal(base.code.slice(0, at) + text + base.code.slice(at + n), editor.getValue());
});

test("typing is batched into one editor.events message every 500 ms", (t) => {
  const { sent, editor, tick } = setup(t);
  editor.edit(0, 0, "d");
  editor.edit(1, 0, "e");
  assert.equal(sent.length, 0);
  tick(BATCH_MS);
  assert.equal(sent.length, 1);
  assert.deepEqual(
    sent[0].events.map((e) => [e.kind, e.version, e.changes[0].text]),
    [
      ["change", 2, "d"],
      ["change", 3, "e"],
    ],
  );
  assert.equal(sent[0].events[0].file, "solution.py");
});

test("a paste relabels its change and counts the pasted characters", (t) => {
  const { sent, editor, tick } = setup(t);
  editor.paste(0, "x = 1\ny = 2\n");
  tick(BATCH_MS);
  const [event] = events(sent);
  assert.equal(event.kind, "paste");
  assert.equal(event.pasted_chars, 12);
});

test("a paste event that arrives first labels the next change", (t) => {
  const { sent, editor, tick } = setup(t);
  for (const listener of editor.pasteListeners) listener({});
  editor.edit(0, 0, "abc");
  tick(BATCH_MS);
  assert.equal(events(sent)[0].kind, "paste");
});

test("undo and redo keep their kinds", (t) => {
  const { sent, editor, tick } = setup(t);
  editor.edit(0, 0, "a");
  editor.edit(0, 1, "", { undo: true });
  editor.edit(0, 0, "a", { redo: true });
  tick(BATCH_MS);
  assert.deepEqual(
    events(sent).map((e) => e.kind),
    ["change", "undo", "redo"],
  );
});

test("a snapshot follows every 20 changes, after the pending events", (t) => {
  const { sent, editor } = setup(t);
  for (let i = 0; i < SNAPSHOT_EVERY_CHANGES; i += 1) editor.edit(i, 0, "x");
  assert.deepEqual(
    sent.map((m) => m.type),
    ["editor.events", "editor.snapshot"],
  );
  assert.equal(snapshots(sent)[0].code, "x".repeat(SNAPSHOT_EVERY_CHANGES));
});

test("a snapshot follows 15 s after the last one when there were changes", (t) => {
  const { sent, editor, tick } = setup(t);
  editor.edit(0, 0, "a");
  tick(SNAPSHOT_IDLE_MS - BATCH_MS);
  assert.equal(snapshots(sent).length, 0);
  tick(BATCH_MS);
  assert.equal(snapshots(sent).length, 1);
});

test("no idle snapshot after the baseline without changes", (t) => {
  const { sent, tick } = setup(t);
  tick(SNAPSHOT_IDLE_MS * 2);
  assert.equal(sent.length, 0);
});

test("snapshot() sends pending events first, then the exact code", (t) => {
  const { capture, sent, editor, clock } = setup(t);
  editor.edit(0, 0, "def f():\n    pass\n");
  clock.ms = 4200;
  capture.snapshot();
  assert.deepEqual(
    sent.map((m) => m.type),
    ["editor.events", "editor.snapshot"],
  );
  assert.deepEqual(snapshots(sent)[0], { t: 4200, file: "solution.py", version: 2, code: "def f():\n    pass\n" });
});

test("a flush (setValue) becomes a snapshot, not typing", (t) => {
  const { sent, editor, tick } = setup(t);
  editor.edit(0, 0, "starter code that the candidate never typed", { flush: true });
  tick(BATCH_MS);
  assert.equal(events(sent).length, 0);
  assert.equal(snapshots(sent).length, 1);
});

test("programmatic() edits are snapshotted, not recorded as edits", (t) => {
  const { capture, sent, editor, tick } = setup(t);
  capture.programmatic(() => editor.edit(0, 0, "reset to the starter code"));
  tick(BATCH_MS);
  assert.equal(events(sent).length, 0);
  assert.equal(snapshots(sent)[0].code, "reset to the starter code");
});

test("visibility and focus changes become editor events", (t) => {
  const { sent, doc, win, tick } = setup(t);
  doc.visibilityState = "hidden";
  doc.dispatchEvent(new Event("visibilitychange"));
  doc.visibilityState = "visible";
  doc.dispatchEvent(new Event("visibilitychange"));
  win.dispatchEvent(new Event("blur"));
  win.dispatchEvent(new Event("focus"));
  tick(BATCH_MS);
  assert.deepEqual(
    events(sent).map((e) => e.kind),
    ["hidden", "visible", "blur", "focus"],
  );
});

test("setFile labels later events with the new file and snapshots it", (t) => {
  const { capture, sent, editor, tick } = setup(t);
  capture.setFile("app/main.py");
  editor.edit(0, 0, "x");
  tick(BATCH_MS);
  assert.equal(snapshots(sent)[0].file, "app/main.py");
  assert.equal(events(sent)[0].file, "app/main.py");
});

test("dispose() flushes and stops listening", (t) => {
  const { capture, sent, editor, tick } = setup(t);
  editor.edit(0, 0, "a");
  capture.dispose();
  assert.equal(events(sent).length, 1);
  editor.edit(1, 0, "b");
  tick(BATCH_MS * 4);
  assert.equal(events(sent).length, 1);
});
