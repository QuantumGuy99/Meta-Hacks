"use client";

import NumberFlow from "@number-flow/react";
import { useState } from "react";
import { toast } from "sonner";
import { LiveLoadChart } from "@/components/defense/LiveLoadChart";
import DecryptedText from "@/components/react-bits/DecryptedText";
import { ActivityIcon } from "@/components/ui/activity";
import {
  audit,
  baselineRun,
  defenseReport,
  finding,
  grillTurn,
  lastMetric,
  missingDollars,
  severityLabel,
  verdict,
  verifyRun,
} from "@/lib/fixtures";

// The bank-transfer fixture's one finding, shown in the three states the chaos lab moves it through.
const plan = finding.chaos!;
const rootCause = defenseReport.moments.find((mo) => mo.kind === "good");

function FindingHead() {
  return (
    <div className="fr-head">
      <span className="sev">{severityLabel(finding.severity)}</span>
      <strong>
        {finding.title} · <code translate="no">{`${plan.method} ${plan.endpoint}`}</code>
      </strong>
      <span className="fr-file" translate="no">
        {finding.file}:{finding.line_start}–{finding.line_end}
      </span>
    </div>
  );
}

export function DefenseRows() {
  const [fixed, setFixed] = useState(false);
  const run = fixed ? verifyRun : baselineRun;
  const metric = lastMetric(run);

  return (
    <div className="fr-stack">
      <div className="fr-group" data-reveal>
        <p className="fr-state">Found</p>
        <div data-ui className="fr">
          <FindingHead />
          {/* the audit summary only: why it breaks stays hidden until the candidate explains it */}
          <p className="fr-line">{audit.summary}</p>
          <div className="fr-foot">
            <span>Audit · Muse Wonder 1.0</span>
            <span>
              Attack queued: {plan.concurrency} concurrent, {plan.duration_s} s
            </span>
          </div>
        </div>
      </div>

      <div className="fr-group" data-reveal>
        <p className="fr-state" aria-live="polite">
          {/* the state word scrambles into place each time the attack result flips */}
          <DecryptedText key={run.verdict} text={run.verdict === "held" ? "Held" : "Broke"} animateOn="view" sequential speed={45} />
        </p>
        <div data-ui className={fixed ? "fr fr-held" : "fr fr-broke fr-hover"}>
          <FindingHead />
          <p className="fr-line" aria-live="polite">
            {run.summary} <span className="fr-detail">({run.detail})</span>
          </p>
          <div className="fr-live">
            <span className="fr-live-label">
              <ActivityIcon size={14} aria-hidden /> Invariant violations, {metric.in_flight} in flight
            </span>
            <LiveLoadChart key={run.id} run={run} metric="violations" height={96} />
          </div>
          <dl className="fr-metrics">
            <div>
              <dt>Violations</dt>
              <dd className={fixed ? "is-ok" : "is-bad"}>
                <NumberFlow value={metric.violations} />
              </dd>
            </div>
            <div>
              <dt>Missing</dt>
              <dd className={fixed ? "is-ok" : "is-bad"}>
                <NumberFlow value={missingDollars(run)} format={{ style: "currency", currency: "USD", maximumFractionDigits: 0 }} />
              </dd>
            </div>
            <div>
              <dt>p95</dt>
              <dd>
                <NumberFlow value={metric.p95_ms} suffix=" ms" />
              </dd>
            </div>
          </dl>
          <div className="fr-foot">
            {fixed ? (
              <span className="gate">Merge gate: {verdict.passed ? "pass" : "fail"}</span>
            ) : (
              <span>Invariant broken: {plan.invariant}</span>
            )}
            <span className="fr-actions">
              <button
                type="button"
                className="ui-btn ui-btn-primary"
                onClick={() => {
                  const next = !fixed;
                  setFixed(next);
                  if (next) toast.success("Attack re-run: the fix held", { description: verifyRun.summary });
                }}
              >
                {fixed ? "Show the Failing Run" : "Apply Fix & Re-run"}
              </button>
            </span>
          </div>
        </div>
      </div>

      <div className="fr-group" data-reveal>
        <p className="fr-state">Defended</p>
        <div data-ui className="fr fr-defended">
          <FindingHead />
          <p className="fr-line">
            <span className="fr-q">“{grillTurn.question}”</span>
            {rootCause && ` ${rootCause.title}: ${rootCause.detail}`}
          </p>
          <div className="fr-foot">
            <span>
              Grill · {grillTurn.score} of 10 · hit {grillTurn.eval.points_hit.length} of{" "}
              {grillTurn.eval.points_hit.length + grillTurn.eval.points_missed.length} expected points
            </span>
            <span className="gate">{verdict.reasons[0]}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
