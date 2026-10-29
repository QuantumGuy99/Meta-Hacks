// Defense-stage selectors (PLAN §11.2): pure functions over the live session state, for the Defense views.
// No fetching and no components. Outcomes such as "Broke" or "Merge approved" are data, not phases.

import type {
  AuditPublic,
  ChaosMetric,
  ChaosRun,
  Finding,
  FindingPublic,
  GrillTurn,
  Phase,
  Verdict,
} from "../types/contracts";

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
export type ChaosPoint = {
  t: number;
  inFlight: number;
  rps: number;
  p95: number;
  p99: number;
  errors: number;
  violations: number;
};
/** A graded grill: `finding` is null when restored from the timeline, which only holds the turn. */
export type GradedGrill = { turn: GrillTurn; finding: Finding | null };
export type NodeStatus = "ok" | "flagged" | "broke" | "verified";

const STAGES: Partial<Record<Phase, DefenseStage>> = {
  audit: "audit",
  chaos: "chaos",
  grill: "grill",
  fix: "fix",
  verify: "verify",
  verdict: "verdict",
  ended: "verdict",
  reporting: "verdict",
  reported: "verdict",
};

/** The stepper's stage for a phase; null before the audit starts (setup) or for coding phases. */
export function defenseStage(phase: Phase | null): DefenseStage | null {
  return (phase && STAGES[phase]) ?? null;
}

/** The header label, from the phase plus the latest data. */
export function stageLabel(phase: Phase | null, runs: ChaosRun[], verdict: Verdict | null): StageLabel | null {
  switch (defenseStage(phase)) {
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
    case "verdict":
      return verdict ? (verdict.passed ? "Merge approved" : "Merge rejected") : null;
    default:
      return null;
  }
}

/** One run's chart points, oldest first: the finished run's own metrics, else the live ones so far. */
export function chaosSeries(runs: ChaosRun[], live: ChaosMetric[], runId: string): ChaosPoint[] {
  const done = runs.find((r) => r.id === runId);
  const source = done && done.metrics.length > 0 ? done.metrics : live.filter((m) => m.run_id === runId);
  const byTime = new Map<number, ChaosMetric>();
  for (const m of source) byTime.set(m.t_ms, m); // a reload can deliver one point twice
  return [...byTime.values()]
    .sort((a, b) => a.t_ms - b.t_ms)
    .map((m) => ({
      t: m.t_ms,
      inFlight: m.in_flight,
      rps: m.rps,
      p95: m.p95_ms,
      p99: m.p99_ms,
      errors: m.errors,
      violations: m.violations,
    }));
}

/** The latest baseline and verify run for a finding, for the before/after charts. */
export function beforeAfter(runs: ChaosRun[], findingId: string): { baseline?: ChaosRun; verify?: ChaosRun } {
  const latest = (kind: ChaosRun["kind"]) =>
    runs.filter((r) => r.finding_id === findingId && r.kind === kind).sort((a, b) => b.attempt - a.attempt)[0];
  return { baseline: latest("baseline"), verify: latest("verify") };
}

/** The banner over a finished run. The summary is the server's own sentence with the real numbers. */
export function verdictBanner(run: ChaosRun): { tone: ChaosRun["verdict"]; text: string } {
  return { tone: run.verdict, text: run.summary };
}

export function flaggedNodeIds(audit: AuditPublic): Set<string> {
  return new Set(audit.findings.flatMap((f) => (f.node_id ? [f.node_id] : [])));
}

/** The public finding, plus the full one (explanation, points, fix steps) only once its grill is graded. */
export function findingDetail(
  audit: AuditPublic,
  grill: GradedGrill[],
  findingId: string,
): { public: FindingPublic | null; full: Finding | null } {
  return {
    public: audit.findings.find((f) => f.id === findingId) ?? null,
    full: grill.find((g) => g.turn.finding_id === findingId)?.finding ?? null,
  };
}

/** A topology node's colour: verified once every broken finding in it held, broke if any broke, else
 * flagged if the audit pointed at it. */
export function nodeStatus(audit: AuditPublic, runs: ChaosRun[], nodeId: string): NodeStatus {
  const findings = audit.findings.filter((f) => f.node_id === nodeId);
  if (findings.length === 0) return "ok";
  const broken = findings.filter((f) => beforeAfter(runs, f.id).baseline?.verdict === "broke");
  if (broken.length === 0) return "flagged";
  return broken.every((f) => beforeAfter(runs, f.id).verify?.verdict === "held") ? "verified" : "broke";
}
