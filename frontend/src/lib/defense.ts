// Defense-stage selectors for the Defense views (PLAN §11.2, §14.3). Pure functions over the session state:
// no fetching and no components. "Broke" and "Merge approved" are data (runs, verdict), not phases.
import type {
  AuditPublic,
  ChaosMetric,
  ChaosRun,
  Finding,
  FindingPublic,
  GrillTurn,
  Phase,
  Verdict,
} from "@/types/contracts";

export type DefenseStage = "audit" | "chaos" | "grill" | "fix" | "verify" | "verdict";
export type StageLabel =
  | "Auditing"
  | "Chaos run"
  | "Broke"
  | "Grill"
  | "Fixing"
  | "Verifying"
  | "Merge approved"
  | "Merge rejected";
export type NodeStatus = "ok" | "flagged" | "broke" | "verified";
// A graded grill turn arrives with its full Finding (defense.grill.eval), never before.
export type GrillTurnWithFinding = { turn: GrillTurn; finding: Finding };
export type ChaosPoint = {
  t: number;
  inFlight: number;
  rps: number;
  p95: number;
  p99: number;
  errors: number;
  violations: number;
};

const STAGES: readonly DefenseStage[] = ["audit", "chaos", "grill", "fix", "verify", "verdict"];
const AFTER_VERDICT: readonly Phase[] = ["ended", "reporting", "reported"];

export function defenseStage(phase: Phase): DefenseStage | null {
  return (STAGES as readonly string[]).includes(phase) ? (phase as DefenseStage) : null;
}

export function stageLabel(phase: Phase, runs: readonly ChaosRun[], verdict: Verdict | null): StageLabel | null {
  if (verdict && (phase === "verdict" || AFTER_VERDICT.includes(phase))) {
    return verdict.passed ? "Merge approved" : "Merge rejected";
  }
  switch (phase) {
    case "audit":
      return "Auditing";
    case "chaos":
      return runs.some((r) => r.kind === "baseline" && r.verdict === "broke") ? "Broke" : "Chaos run";
    case "grill":
      return "Grill";
    case "fix":
      return "Fixing";
    case "verify":
      return "Verifying";
    default:
      return null;
  }
}

// The chart points for one run: the finished run's own metrics, else the live ones streamed so far.
export function chaosSeries(runs: readonly ChaosRun[], live: readonly ChaosMetric[], runId: string): ChaosPoint[] {
  const done = runs.find((r) => r.id === runId);
  const metrics = done && done.metrics.length > 0 ? done.metrics : live.filter((m) => m.run_id === runId);
  return [...metrics]
    .sort((a, b) => a.t_ms - b.t_ms)
    .map((m) => ({
      t: m.t_ms / 1000,
      inFlight: m.in_flight,
      rps: m.rps,
      p95: m.p95_ms,
      p99: m.p99_ms,
      errors: m.errors,
      violations: m.violations,
    }));
}

// The latest baseline and the latest verify run for a finding (verify can run up to 3 times).
export function beforeAfter(runs: readonly ChaosRun[], findingId: string): { baseline?: ChaosRun; verify?: ChaosRun } {
  return { baseline: latest(runs, findingId, "baseline"), verify: latest(runs, findingId, "verify") };
}

export function verdictBanner(run: ChaosRun): { tone: "broke" | "held" | "error"; text: string } {
  return { tone: run.verdict, text: run.summary };
}

export function flaggedNodeIds(audit: AuditPublic): Set<string> {
  const ids = new Set(audit.nodes.filter((n) => n.flagged).map((n) => n.id));
  for (const f of audit.findings) if (f.node_id) ids.add(f.node_id);
  return ids;
}

export function findingDetail(
  audit: AuditPublic,
  grill: readonly GrillTurnWithFinding[],
  findingId: string,
): { public: FindingPublic; full: Finding | null } | null {
  const pub = audit.findings.find((f) => f.id === findingId);
  if (!pub) return null;
  const graded = grill.find((g) => g.turn.finding_id === findingId);
  return { public: pub, full: graded ? graded.finding : null };
}

export function nodeStatus(audit: AuditPublic, runs: readonly ChaosRun[], nodeId: string): NodeStatus {
  const findings = audit.findings.filter((f) => f.node_id === nodeId);
  if (findings.length === 0) {
    return audit.nodes.some((n) => n.id === nodeId && n.flagged) ? "flagged" : "ok";
  }
  if (findings.every((f) => latest(runs, f.id, "verify")?.verdict === "held")) return "verified";
  if (findings.some((f) => latest(runs, f.id, "baseline")?.verdict === "broke")) return "broke";
  return "flagged";
}

function latest(runs: readonly ChaosRun[], findingId: string, kind: ChaosRun["kind"]): ChaosRun | undefined {
  let best: ChaosRun | undefined;
  for (const r of runs) {
    if (r.finding_id === findingId && r.kind === kind && (!best || r.attempt >= best.attempt)) best = r;
  }
  return best;
}
