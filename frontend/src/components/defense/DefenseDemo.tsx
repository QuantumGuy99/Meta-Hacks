"use client";

import NumberFlow from "@number-flow/react";
import { AnimatePresence, m } from "motion/react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { LiveLoadChart } from "./LiveLoadChart";
import { TopologyView, type TopoEdge, type TopoNode } from "./TopologyView";

// Scripted Project Defense flow for the bank-transfer sample app (FE-6 shape, mock data).

const NODES: TopoNode[] = [
  { id: "r-transfer", label: "POST /transfer", kind: "route", file: "app/routes/transfer.py", flagged: false },
  { id: "r-balance", label: "GET /balance", kind: "route", file: "app/routes/balance.py", flagged: false },
  { id: "s-transfer", label: "TransferService", kind: "service", file: "app/services/transfer.py", flagged: true },
  { id: "s-audit", label: "AuditLog", kind: "worker", file: "app/workers/audit.py", flagged: false },
  { id: "db", label: "accounts (SQLite)", kind: "store", file: "app/db.py", flagged: false },
  { id: "x-notify", label: "Email API", kind: "external", file: null, flagged: false },
];

const EDGES: TopoEdge[] = [
  { source: "r-transfer", target: "s-transfer", label: "debit + credit" },
  { source: "r-balance", target: "db", label: "read" },
  { source: "s-transfer", target: "db", label: "read, write" },
  { source: "s-transfer", target: "s-audit", label: "enqueue" },
  { source: "s-audit", target: "x-notify", label: null },
];

const STAGES = ["Audit", "Chaos", "Grill", "Verdict"] as const;
type Stage = (typeof STAGES)[number];

const GRILL_POINTS = [
  "Both requests read the balance before either writes",
  "The read-modify-write needs to be atomic",
  "A transaction with a row lock, or an atomic UPDATE",
];

export function DefenseDemo() {
  const [stage, setStage] = useState<Stage>("Audit");
  const [selected, setSelected] = useState<string | null>("s-transfer");
  const [fixed, setFixed] = useState(false);
  const [answer, setAnswer] = useState("");
  const [graded, setGraded] = useState<number | null>(null);
  const [hitFlags, setHitFlags] = useState<boolean[]>([]);
  const [left, setLeft] = useState(90);

  // 90 s grill countdown while that stage is open and unanswered.
  useEffect(() => {
    if (stage !== "Grill" || graded !== null) return;
    const id = window.setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => window.clearInterval(id);
  }, [stage, graded]);

  const node = NODES.find((n) => n.id === selected);
  const passed = fixed && (graded ?? 0) >= 6;

  const grade = () => {
    const a = answer.toLowerCase();
    // Stand-in for the backend's GrillEval: one pattern per expected point.
    const flags = [/(both|two).*(read|check)|read.*before/, /atomic|race|interleav/, /lock|transaction|update .* where/].map((r) => r.test(a));
    const hits = flags.filter(Boolean).length;
    const score = Math.min(10, 3 + hits * 2 + (answer.length > 80 ? 1 : 0));
    setHitFlags(flags);
    setGraded(score);
    toast[score >= 6 ? "success" : "warning"](`Grill scored ${score} of 10`, { description: `${hits} of 3 expected points hit.` });
  };

  return (
    <div className="df" data-ui>
      <header className="rm-top">
        <Link href="/" className="rm-brand" translate="no">
          Crucible
        </Link>
        <ol className="df-stages" aria-label="Defense stages">
          {STAGES.map((s) => (
            <li key={s}>
              <button type="button" aria-current={s === stage ? "step" : undefined} onClick={() => setStage(s)}>
                {s}
              </button>
            </li>
          ))}
        </ol>
        <span className="room-badge">bank-transfer · Demo</span>
      </header>

      <AnimatePresence mode="wait" initial={false}>
        <m.section
          key={stage}
          className="df-stage"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          aria-label={`${stage} stage`}
        >
          {stage === "Audit" && (
            <div className="df-audit">
              <div className="df-topo">
                <TopologyView nodes={NODES} edges={EDGES} selectedId={selected} onSelect={setSelected} />
              </div>
              <aside className="df-side">
                <h2>Findings</h2>
                <button type="button" className="df-finding is-on" onClick={() => setSelected("s-transfer")}>
                  <span className="sev">High</span>
                  <strong>Race condition in TransferService</strong>
                  <span className="df-muted" translate="no">
                    app/services/transfer.py:41–58
                  </span>
                </button>
                {node && (
                  <div className="df-detail">
                    <h3>{node.label}</h3>
                    <p>
                      {node.flagged
                        ? "Balances are read, changed and written back without a lock. Two transfers from the same account can both pass the balance check."
                        : "No issues found in this component."}
                    </p>
                  </div>
                )}
                <button type="button" className="ui-btn ui-btn-primary" onClick={() => setStage("Chaos")}>
                  Run the Attack
                </button>
              </aside>
            </div>
          )}

          {stage === "Chaos" && (
            <div className="df-chaos">
              <div className={`df-banner ${fixed ? "is-held" : "is-broke"}`} aria-live="polite">
                <strong>{fixed ? "HELD" : "BROKE"}</strong>
                {fixed ? "500 of 500 transfers applied; balances still sum to $10,000." : "Under 200 concurrent transfers, $1,240 disappeared."}
              </div>
              <div className="df-chart">
                <div className="df-legend">
                  <span className={fixed ? "lg-ok" : "lg-bad"}>p95 latency (ms)</span>
                  <span className="lg-rps">requests/s</span>
                </div>
                <LiveLoadChart mode={fixed ? "held" : "broke"} height={240} showRps />
              </div>
              <dl className="fr-metrics df-metrics">
                <div>
                  <dt>Requests/s</dt>
                  <dd>
                    <NumberFlow value={fixed ? 652 : 548} />
                  </dd>
                </div>
                <div>
                  <dt>p95</dt>
                  <dd>
                    <NumberFlow value={fixed ? 38 : 412} suffix=" ms" />
                  </dd>
                </div>
                <div>
                  <dt>Invariant violations</dt>
                  <dd className={fixed ? "is-ok" : "is-bad"}>
                    <NumberFlow value={fixed ? 0 : 37} />
                  </dd>
                </div>
              </dl>
              <div className="df-row">
                {!fixed ? (
                  <button type="button" className="ui-btn" onClick={() => setStage("Grill")}>
                    Explain the Failure
                  </button>
                ) : (
                  <button type="button" className="ui-btn ui-btn-primary" onClick={() => setStage("Verdict")}>
                    See the Verdict
                  </button>
                )}
                <button
                  type="button"
                  className="ui-btn"
                  onClick={() => {
                    setFixed((f) => !f);
                    toast[fixed ? "info" : "success"](fixed ? "Showing the baseline attack" : "Verify run: the fix held");
                  }}
                >
                  {fixed ? "Show Baseline Run" : "Apply Fix & Verify"}
                </button>
              </div>
            </div>
          )}

          {stage === "Grill" && (
            <div className="df-grill">
              <div className="df-q">
                <span className="df-muted">
                  Question · <NumberFlow value={left} suffix=" s" /> left
                </span>
                <h2>Why did $1,240 disappear under 200 concurrent transfers, and what would you change?</h2>
              </div>
              <label className="df-answer">
                <span>Your answer</span>
                <textarea
                  name="answer"
                  rows={5}
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  placeholder="Both requests read the balance before either wrote…"
                  disabled={graded !== null}
                />
              </label>
              <div className="df-row">
                <button type="button" className="ui-btn ui-btn-primary" onClick={grade} disabled={!answer.trim() || graded !== null}>
                  Submit Answer
                </button>
                {graded !== null && (
                  <button type="button" className="ui-btn" onClick={() => setStage("Chaos")}>
                    Go Fix It
                  </button>
                )}
              </div>
              {graded !== null && (
                <ul className="df-points" aria-live="polite">
                  {GRILL_POINTS.map((p, i) => {
                    const hit = hitFlags[i];
                    return (
                      <li key={p} className={hit ? "is-hit" : "is-miss"}>
                        <span>{hit ? "Hit" : "Missed"}</span>
                        {p}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          )}

          {stage === "Verdict" && (
            <div className="df-verdict">
              <div className={`df-gate ${passed ? "is-pass" : "is-fail"}`}>
                <span className="df-muted">Merge gate</span>
                <strong>{passed ? "PASS" : "FAIL"}</strong>
              </div>
              <ul className="df-reasons">
                <li className={fixed ? "is-hit" : "is-miss"}>
                  <span>{fixed ? "Met" : "Not met"}</span>Every grilled finding verified fixed under the same attack
                </li>
                <li className={(graded ?? 0) >= 6 ? "is-hit" : "is-miss"}>
                  <span>{(graded ?? 0) >= 6 ? "Met" : "Not met"}</span>Average grill score at least 6 of 10 (
                  {graded === null ? "not answered" : <NumberFlow value={graded} />})
                </li>
              </ul>
              <Link href="/report/demo" className="ui-btn ui-btn-primary">
                Open the Report
              </Link>
            </div>
          )}
        </m.section>
      </AnimatePresence>
    </div>
  );
}
