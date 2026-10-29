// Defense selectors over a real recorded session: the same MOCK fixture the backend replays (PLAN §14.6).
// Run: node --experimental-strip-types --test "frontend/src/lib/**/*.test.mjs"
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  beforeAfter,
  chaosSeries,
  defenseStage,
  findingDetail,
  flaggedNodeIds,
  nodeStatus,
  stageLabel,
  verdictBanner,
} from "../defense.ts";

const fixture = new URL("../../../../backend/crucible/mock/fixtures/defense-bank-transfer.jsonl", import.meta.url);
const messages = readFileSync(fixture, "utf8")
  .split("\n")
  .filter(Boolean)
  .map((line) => JSON.parse(line).msg);

/** The session state after the first `count` messages, folded the way the room's reducer does. */
function stateAfter(count = messages.length) {
  const s = { phase: null, audit: null, metrics: [], runs: [], grill: [], verdict: null };
  for (const m of messages.slice(0, count)) {
    if (m.type === "session.state") s.phase = m.phase;
    if (m.type === "defense.audit") s.audit = m.audit;
    if (m.type === "defense.chaos.metric") s.metrics.push(m.metric);
    if (m.type === "defense.chaos.done") s.runs.push(m.run);
    if (m.type === "defense.grill.eval") s.grill.push({ turn: m.turn, finding: m.finding });
    if (m.type === "defense.verdict") s.verdict = m.verdict;
  }
  return s;
}
const indexOf = (type, pred = () => true) => messages.findIndex((m) => m.type === type && pred(m)) + 1;
const final = stateAfter();
const finding = final.audit.findings[0];
const baseline = final.runs.find((r) => r.kind === "baseline");

test("stages follow the phases, and coding or setup phases have none", () => {
  assert.equal(defenseStage("audit"), "audit");
  assert.equal(defenseStage("reported"), "verdict");
  assert.equal(defenseStage("setup"), null);
  assert.equal(defenseStage("coding"), null);
  assert.equal(defenseStage(null), null);
});

test("the label says Broke only once a baseline broke, and the verdict decides the end", () => {
  const chaosStarted = stateAfter(indexOf("session.state", (m) => m.phase === "chaos"));
  assert.equal(stageLabel(chaosStarted.phase, chaosStarted.runs, null), "Chaos run");
  const broke = stateAfter(indexOf("defense.chaos.done"));
  assert.equal(stageLabel(broke.phase, broke.runs, null), "Broke");
  assert.equal(stageLabel("verdict", final.runs, null), null); // the verdict hasn't arrived yet
  assert.equal(stageLabel(final.phase, final.runs, final.verdict), "Merge approved");
  assert.equal(stageLabel("ended", final.runs, { ...final.verdict, passed: false }), "Merge rejected");
});

test("a live chart uses the streamed metrics, a finished one its own, sorted and without repeats", () => {
  const live = stateAfter(indexOf("defense.chaos.done") - 1);
  const series = chaosSeries(live.runs, [...live.metrics, live.metrics[0]], baseline.id);
  assert.equal(series.length, live.metrics.filter((m) => m.run_id === baseline.id).length);
  assert.deepEqual(series.map((p) => p.t), [...series.map((p) => p.t)].sort((a, b) => a - b));
  assert.ok(chaosSeries(final.runs, [], baseline.id).length > 0);
});

test("before and after pick the finding's baseline and verify runs", () => {
  const { baseline: before, verify: after } = beforeAfter(final.runs, finding.id);
  assert.equal(before.verdict, "broke");
  assert.equal(after.verdict, "held");
  assert.deepEqual(beforeAfter(final.runs, "nope"), { baseline: undefined, verify: undefined });
  assert.deepEqual(verdictBanner(before), { tone: "broke", text: before.summary });
});

test("the full finding only exists after its grill is graded", () => {
  const beforeGrill = stateAfter(indexOf("defense.grill.eval") - 1);
  assert.equal(findingDetail(beforeGrill.audit, beforeGrill.grill, finding.id).full, null);
  const after = findingDetail(final.audit, final.grill, finding.id);
  assert.equal(after.public.id, finding.id);
  assert.ok(after.full.explanation.length > 0);
});

test("a node goes flagged → broke → verified as the runs come in", () => {
  const node = finding.node_id;
  assert.ok(flaggedNodeIds(final.audit).has(node));
  assert.equal(nodeStatus(final.audit, [], node), "flagged");
  assert.equal(nodeStatus(final.audit, [baseline], node), "broke");
  assert.equal(nodeStatus(final.audit, final.runs, node), "verified");
  assert.equal(nodeStatus(final.audit, final.runs, "no-such-node"), "ok");
});
