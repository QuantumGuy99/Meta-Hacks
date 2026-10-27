// Replay parity: the same checkpoints as backend/tests/engine/test_codestate.py, from the same fixture.
// Run: node --experimental-strip-types --test "frontend/src/lib/**/*.test.mjs"
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { applyChanges, codeAt } from "../replay.ts";

const fixture = new URL("../../../../backend/tests/fixtures/replay_case.json", import.meta.url);
const replayCase = JSON.parse(readFileSync(fixture, "utf8"));

test("every replay checkpoint matches the shared fixture", () => {
  for (const point of replayCase.checkpoints) {
    assert.equal(codeAt(replayCase.events, point.file, point.t), point.code, point.note);
  }
});

test("changes apply from the highest offset down", () => {
  const event = {
    t: 0,
    version: 2,
    kind: "change",
    changes: [
      { range_offset: 1, range_length: 1, text: "a" },
      { range_offset: 3, range_length: 1, text: "b" },
    ],
  };
  assert.equal(applyChanges("0123", event), "0a2b");
});
