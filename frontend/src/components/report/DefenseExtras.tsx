"use client";

import { LiveLoadChart } from "@/components/defense/LiveLoadChart";
import { levelLabel, severityLabel } from "@/lib/fixtures";
import type { ChaosRun, DefenseExtra } from "@/types/contracts";

// The defense part of the report (PLAN §14.5): the merge gate and its reasons, then per finding what broke,
// the attack before and after the fix, and the grill (question, points hit and missed, score).

const latest = (runs: ChaosRun[], findingId: string, kind: ChaosRun["kind"]) =>
  runs.filter((r) => r.finding_id === findingId && r.kind === kind).at(-1) ?? null;

export function DefenseExtras({ defense }: { defense: DefenseExtra }) {
  const { verdict } = defense;
  return (
    <section className="rp-defense" aria-labelledby="rp-defense-title">
      <div className="rp-defense-head">
        <div className={`df-gate ${verdict.passed ? "is-pass" : "is-fail"}`}>
          <span className="df-muted">Merge gate</span>
          <strong>{verdict.passed ? "PASS" : "FAIL"}</strong>
        </div>
        <div>
          <h2 id="rp-defense-title">Defense</h2>
          <p className="df-muted">
            {verdict.findings_fixed.length} of {defense.findings.length} findings fixed · grill average{" "}
            {verdict.avg_grill_score.toFixed(1)} of 10
          </p>
          <ul className="df-reasons">
            {verdict.reasons.map((r) => (
              <li key={r} className={verdict.passed ? "is-hit" : "is-miss"}>
                <span>{verdict.passed ? "Met" : "Note"}</span>
                {r}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {defense.findings.map((f) => {
        const before = latest(defense.chaos_runs, f.id, "baseline");
        const after = latest(defense.chaos_runs, f.id, "verify");
        const grill = defense.grill.find((g) => g.finding_id === f.id) ?? null;
        const fixed = verdict.findings_fixed.includes(f.id);
        return (
          <article key={f.id} className="rp-finding">
            <header>
              <span className="sev">{severityLabel(f.severity)}</span>
              <h3>{f.title}</h3>
              <span className={fixed ? "rp-chip is-ok" : "rp-chip is-bad"}>{fixed ? "Fixed" : "Still open"}</span>
              <span className="df-muted" translate="no">
                {levelLabel(f.category.replace(/_/g, " "))} · {f.file}:{f.line_start}–{f.line_end}
              </span>
            </header>
            <p>{f.explanation}</p>

            {before && (
              <div className="df-chart">
                <div className="df-legend">
                  <span className={after?.verdict === "held" ? "lg-ok" : "lg-bad"}>
                    Invariant violations{after ? ", after the fix" : ""}
                  </span>
                  {after && <span className="lg-before">Before the fix</span>}
                </div>
                <LiveLoadChart run={after ?? before} compare={after ? before : undefined} metric="violations" height={180} />
                <dl className="rp-runs">
                  <div>
                    <dt>Before: {before.verdict}</dt>
                    <dd>{before.summary}</dd>
                  </div>
                  <div>
                    <dt>After: {after ? after.verdict : "not verified"}</dt>
                    <dd>{after ? after.summary : "The fix was never re-attacked."}</dd>
                  </div>
                </dl>
              </div>
            )}

            {grill ? (
              <div className="rp-grill">
                <p className="df-muted">
                  Grill · scored {grill.score} of 10
                  {grill.follow_up_asked ? " · with a follow-up" : ""}
                </p>
                <p className="rp-grill-q">{grill.question}</p>
                <ul className="df-points">
                  {f.grill.expected_points.map((p, i) => {
                    const hit = grill.eval.points_hit.includes(i);
                    return (
                      <li key={p} className={hit ? "is-hit" : "is-miss"}>
                        <span>{hit ? "Hit" : "Missed"}</span>
                        {p}
                      </li>
                    );
                  })}
                </ul>
                {grill.eval.feedback && <p>{grill.eval.feedback}</p>}
              </div>
            ) : (
              <p className="df-muted">Not grilled: the attack didn&apos;t break this one.</p>
            )}
          </article>
        );
      })}
    </section>
  );
}
