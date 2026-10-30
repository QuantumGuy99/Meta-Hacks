// Tests for lib/defense.ts (PLAN §11.2) on the shapes the defense.* messages carry.
// Run: node --experimental-strip-types --test "frontend/src/lib/**/*.test.mjs"
import assert from "node:assert/strict";
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

const metric = (run_id, t_ms, extra = {}) => ({
  run_id, t_ms, in_flight: 10, rps: 100, p50_ms: 5, p95_ms: 40, p99_ms: 80, errors: 0, violations: 0, ...extra,
});
const run = (id, kind, verdict, attempt = 1, finding_id = "f1", metrics = []) => ({
  id, finding_id, kind, attempt, script: "", verdict, summary: `${kind} ${verdict}`, detail: "", metrics,
});
const finding = (id, node_id) => ({
  id, title: "Balance transfers under load", category: "race_condition", severity: "critical",
  file: "app/services.py", line_start: 30, line_end: 52, node_id,
});
const audit = {
  summary: "1 area of this project needs a closer look under load.",
  nodes: [
    { id: "app.services", label: "services.py", kind: "service", file: "app/services.py", flagged: true },
    { id: "app.store", label: "store.py", kind: "store", file: "app/store.py", flagged: false },
  ],
  edges: [],
  findings: [finding("f1", "app.services")],
};

test("defenseStage maps only the defense phases", () => {
  assert.equal(defenseStage("chaos"), "chaos");
  assert.equal(defenseStage("coding"), null);
  assert.equal(defenseStage("ended"), null);
});

test("stageLabel says Broke only once a baseline broke, and the merge verdict after it", () => {
  assert.equal(stageLabel("chaos", [], null), "Chaos run");
  assert.equal(stageLabel("chaos", [run("r1", "baseline", "broke")], null), "Broke");
  assert.equal(stageLabel("chaos", [run("r1", "baseline", "held")], null), "Chaos run");
  const passed = { passed: true, reasons: [], findings_fixed: ["f1"], findings_unfixed: [], avg_grill_score: 9 };
  assert.equal(stageLabel("verdict", [], passed), "Merge approved");
  assert.equal(stageLabel("reported", [], { ...passed, passed: false }), "Merge rejected");
  assert.equal(stageLabel("verdict", [], null), null);
  assert.equal(stageLabel("coding", [], null), null);
});

test("chaosSeries uses live metrics until the run is done, sorted, for that run only", () => {
  const live = [metric("r1", 1000), metric("r2", 500), metric("r1", 500, { violations: 3 })];
  const points = chaosSeries([], live, "r1");
  assert.deepEqual(points.map((p) => p.t), [0.5, 1]);
  assert.equal(points[0].violations, 3);
  const done = run("r1", "baseline", "broke", 1, "f1", [metric("r1", 250)]);
  assert.deepEqual(chaosSeries([done], live, "r1").map((p) => p.t), [0.25]);
});

test("beforeAfter picks the latest attempt of each kind for the finding", () => {
  const runs = [
    run("b", "baseline", "broke"),
    run("v1", "verify", "broke", 1),
    run("v2", "verify", "held", 2),
    run("x", "verify", "held", 3, "f2"),
  ];
  const { baseline, verify } = beforeAfter(runs, "f1");
  assert.equal(baseline.id, "b");
  assert.equal(verify.id, "v2");
  assert.deepEqual(beforeAfter([], "f1"), { baseline: undefined, verify: undefined });
});

test("verdictBanner carries the run's own summary", () => {
  assert.deepEqual(verdictBanner(run("r", "baseline", "error")), { tone: "error", text: "baseline error" });
});

test("flaggedNodeIds includes flagged nodes and every finding's node", () => {
  const withExtra = { ...audit, findings: [...audit.findings, finding("f2", "app.store")] };
  assert.deepEqual([...flaggedNodeIds(withExtra)].sort(), ["app.services", "app.store"]);
});

test("findingDetail reveals the full finding only after its grill is graded", () => {
  assert.equal(findingDetail(audit, [], "f1").full, null);
  const full = { ...finding("f1", "app.services"), explanation: "x", chaos: null, grill: {}, fix_steps: [] };
  const turn = { finding_id: "f1" };
  assert.equal(findingDetail(audit, [{ turn, finding: full }], "f1").full, full);
  assert.equal(findingDetail(audit, [], "nope"), null);
});

test("nodeStatus moves flagged → broke → verified", () => {
  assert.equal(nodeStatus(audit, [], "app.services"), "flagged");
  assert.equal(nodeStatus(audit, [run("b", "baseline", "broke")], "app.services"), "broke");
  const fixed = [run("b", "baseline", "broke"), run("v", "verify", "held")];
  assert.equal(nodeStatus(audit, fixed, "app.services"), "verified");
  assert.equal(nodeStatus(audit, fixed, "app.store"), "ok");
});
