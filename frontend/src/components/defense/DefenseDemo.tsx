"use client";

import NumberFlow from "@number-flow/react";
import { AnimatePresence, m } from "motion/react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type RefObject } from "react";
import { toast } from "sonner";
import DecryptedText from "@/components/react-bits/DecryptedText";
import { CodeEditor } from "@/components/room/CodeEditor";
import { LiquidGlass } from "@/components/theme/LiquidGlass";
import { attachEditorCapture, type EditorCapture } from "@/lib/capture/editor";
import {
  attackFunctions,
  audit,
  BANK_FILES,
  baselineRun,
  finding,
  grillTurn,
  lastMetric,
  project,
  severityLabel,
  transferIsAtomic,
  verifyRun,
} from "@/lib/fixtures";
import type { ChaosRun, Phase } from "@/types/contracts";
import { LiveLoadChart } from "./LiveLoadChart";
import { TopologyView } from "./TopologyView";

// Scripted Project Defense flow on the shared bank-transfer fixture, in the phase order of PLAN §11.2:
// audit → chaos → grill → fix → verify → verdict. Until the grill is graded the browser only has the
// public finding (no explanation, no expected points), the same as AuditPublic over the socket.

const STAGES: { phase: Phase; name: string }[] = [
  { phase: "audit", name: "Audit" },
  { phase: "chaos", name: "Chaos" },
  { phase: "grill", name: "Grill" },
  { phase: "fix", name: "Fix" },
  { phase: "verify", name: "Verify" },
  { phase: "verdict", name: "Verdict" },
];

const category = (c: string) => c.replaceAll("_", " ");
const FLAGS = Object.fromEntries(
  audit.findings.filter((f) => f.node_id).map((f) => [f.node_id as string, category(f.category)]),
);
const POINTS = finding.grill.expected_points;
// Stand-in for the backend's GrillEval: one pattern per expected point ([0] is always the root cause).
const POINT_PATTERNS = [
  /read.*(await|before)|read-modify-write|race/,
  /concurren|stale|overwrite|same balance/,
  /lock|transaction|atomic/,
];
const PASS_SCORE = 6;
const MAX_FIX_ROUNDS = 3; // the first fix plus at most 2 extra rounds (PLAN §11.2)
const FILES = Object.keys(BANK_FILES);
const FIX = finding.fix_steps[0];

type Grade = { hits: boolean[]; score: number; rootCause: boolean; samBonus: boolean };

/**
 * The stage label the header shows, from the phase plus the latest data. lib/defense.ts (SS) will own
 * this selector; outcomes such as "Broke" or "Merge approved" are data, not phases.
 */
function stageLabel(phase: Phase, verified: ChaosRun | null, passed: boolean) {
  switch (phase) {
    case "audit":
      return "Auditing";
    case "chaos":
      return baselineRun.verdict === "broke" ? "Broke" : "Chaos run";
    case "grill":
      return "Grill";
    case "fix":
      return "Fixing";
    case "verify":
      return verified ? (verified.verdict === "held" ? "Held" : "Still broke") : "Verifying";
    default:
      return passed ? "Merge approved" : "Merge rejected";
  }
}

/** "Circle it": a pen over the topology. Code picks the node with the largest overlap, as after SAM. */
function CirclePen({ host, onCircle }: { host: RefObject<HTMLElement | null>; onCircle: (nodeId: string | null) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const points = useRef<{ x: number; y: number }[]>([]);

  const local = (e: ReactPointerEvent) => {
    const r = canvas.current!.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  const ctx = () => {
    const c = canvas.current!;
    const r = c.getBoundingClientRect();
    if (c.width !== r.width || c.height !== r.height) {
      c.width = r.width;
      c.height = r.height;
    }
    const g = c.getContext("2d")!;
    g.strokeStyle = "#ffffff";
    g.lineWidth = 3;
    g.lineCap = "round";
    g.lineJoin = "round";
    return g;
  };

  return (
    <canvas
      ref={canvas}
      className="df-pen"
      aria-label="Drawing surface: circle the part of the diagram you think broke"
      onPointerDown={(e) => {
        try {
          e.currentTarget.setPointerCapture(e.pointerId); // keep the stroke if it leaves the canvas
        } catch {
          // synthetic or already-released pointers can't be captured; drawing still works
        }
        const p = local(e);
        points.current = [p];
        const g = ctx();
        g.clearRect(0, 0, g.canvas.width, g.canvas.height);
        g.beginPath();
        g.moveTo(p.x, p.y);
      }}
      onPointerMove={(e) => {
        if (!points.current.length) return;
        const p = local(e);
        points.current.push(p);
        const g = ctx();
        g.lineTo(p.x, p.y);
        g.stroke();
      }}
      onPointerUp={() => {
        const pts = points.current;
        points.current = [];
        if (pts.length < 4 || !host.current || !canvas.current) return onCircle(null);
        const origin = canvas.current.getBoundingClientRect();
        const box = {
          left: origin.left + Math.min(...pts.map((p) => p.x)),
          right: origin.left + Math.max(...pts.map((p) => p.x)),
          top: origin.top + Math.min(...pts.map((p) => p.y)),
          bottom: origin.top + Math.max(...pts.map((p) => p.y)),
        };
        // Largest intersection over node area, at least 0.3 (PLAN §11.7).
        let best: { id: string; ratio: number } | null = null;
        host.current.querySelectorAll<HTMLElement>(".react-flow__node").forEach((el) => {
          const n = el.getBoundingClientRect();
          const w = Math.max(0, Math.min(box.right, n.right) - Math.max(box.left, n.left));
          const h = Math.max(0, Math.min(box.bottom, n.bottom) - Math.max(box.top, n.top));
          const ratio = (w * h) / (n.width * n.height);
          const id = el.dataset.id;
          if (id && ratio >= 0.3 && (!best || ratio > best.ratio)) best = { id, ratio };
        });
        onCircle((best as { id: string; ratio: number } | null)?.id ?? null);
      }}
    />
  );
}

export function DefenseDemo() {
  const [stage, setStage] = useState<Phase>("audit");
  const [selected, setSelected] = useState<string | null>(finding.node_id);
  const [answer, setAnswer] = useState("");
  const [grade, setGrade] = useState<Grade | null>(null);
  const [left, setLeft] = useState(90);
  const [pen, setPen] = useState(false);
  const [circled, setCircled] = useState<string | null>(null);
  const [files, setFiles] = useState(BANK_FILES);
  const [activeFile, setActiveFile] = useState(finding.file);
  const [hintsShown, setHintsShown] = useState(0);
  const [verified, setVerified] = useState<ChaosRun | null>(null);
  const [rounds, setRounds] = useState(0);
  const [captured, setCaptured] = useState(0);
  const topoHost = useRef<HTMLDivElement>(null);
  const editor = useRef<Parameters<NonNullable<Parameters<typeof CodeEditor>[0]["onEditor"]>>[0] | null>(null);
  const capture = useRef<EditorCapture | null>(null);
  const openPath = useRef(activeFile);

  // 90 s grill countdown while that stage is open and unanswered.
  useEffect(() => {
    if (stage !== "grill" || grade !== null) return;
    const id = window.setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => window.clearInterval(id);
  }, [stage, grade]);

  useEffect(() => () => capture.current?.dispose(), []);

  const node = audit.nodes.find((n) => n.id === selected);
  const nodeFinding = audit.findings.find((f) => f.node_id === selected);
  const baseline = lastMetric(baselineRun);
  const passed = verified?.verdict === "held" && (grade?.score ?? 0) >= PASS_SCORE && !!grade?.rootCause;
  const label = stageLabel(stage, verified, passed);

  const submitAnswer = () => {
    const a = answer.toLowerCase();
    const hits = POINT_PATTERNS.map((r) => r.test(a));
    // Scoring is code, not the model (PLAN §11.5): share of points hit, +1 for circling the right node.
    const samBonus = circled !== null && circled === finding.node_id;
    const score = Math.min(10, Math.round((10 * hits.filter(Boolean).length) / POINTS.length) + (samBonus ? 1 : 0));
    setGrade({ hits, score, rootCause: hits[0], samBonus });
    toast[score >= PASS_SCORE ? "success" : "warning"](`Grill scored ${score} of 10`, {
      description: `${hits.filter(Boolean).length} of ${POINTS.length} expected points${samBonus ? ", +1 for circling it" : ""}.`,
    });
  };

  const onEditor = useCallback((ed: NonNullable<typeof editor.current>) => {
    editor.current = ed;
    capture.current?.dispose();
    capture.current = attachEditorCapture(
      ed,
      (msg) => setCaptured((n) => n + (msg.type === "editor.events" ? msg.events.length : 1)),
      // the editor remounts on each visit to Fix, on whichever file was open
      { startedAtMs: Date.now(), file: openPath.current },
    );
  }, []);

  // Each tab is its own Monaco model (CodeEditor's path), so switching is a model swap, not an edit.
  // Once the swap has rendered, setFile tells the capture lib (it snapshots the newly open file).
  const openFile = (path: string) => {
    openPath.current = path;
    setActiveFile(path);
  };
  useEffect(() => {
    capture.current?.setFile(activeFile);
  }, [activeFile]);

  const verify = () => {
    capture.current?.snapshot();
    const main = activeFile === "app/main.py" ? (editor.current?.getValue() ?? files["app/main.py"]) : files["app/main.py"];
    const attempt = rounds + 1;
    const run: ChaosRun = transferIsAtomic(main)
      ? { ...verifyRun, attempt }
      : { ...baselineRun, id: `c-verify-${attempt}`, kind: "verify", attempt };
    setRounds(attempt);
    setVerified(run);
    setStage("verify");
    toast[run.verdict === "held" ? "success" : "error"](run.verdict === "held" ? "Verify held" : "Verify broke again", {
      description: run.summary,
    });
  };

  return (
    <div className="df" data-ui>
      <header className="rm-top">
        <Link href="/" className="rm-brand" translate="no">
          Crucible
        </Link>
        <ol className="df-stages" aria-label="Defense stages">
          {STAGES.map((s) => (
            <li key={s.phase}>
              <button type="button" aria-current={s.phase === stage ? "step" : undefined} onClick={() => setStage(s.phase)}>
                {s.name}
              </button>
            </li>
          ))}
        </ol>
        <span className="df-label" aria-live="polite">
          {label}
        </span>
        <span className="room-badge" translate="no">
          {project.name} · {project.loc} lines · Demo
        </span>
      </header>

      <AnimatePresence mode="wait" initial={false}>
        <m.section
          key={stage}
          className="df-stage"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          aria-label={`${label} stage`}
        >
          {stage === "audit" && (
            <div className="df-audit">
              <div className="df-topo">
                <TopologyView nodes={audit.nodes} edges={audit.edges} selectedId={selected} onSelect={setSelected} flags={FLAGS} />
              </div>
              <aside className="df-side">
                <h2>Findings</h2>
                <p className="df-muted">{audit.summary}</p>
                {audit.findings.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    className={f.node_id === selected ? "df-finding is-on" : "df-finding"}
                    onClick={() => setSelected(f.node_id)}
                  >
                    <span className="sev">{severityLabel(f.severity)}</span>
                    <strong>{f.title}</strong>
                    <span className="df-muted" translate="no">
                      {category(f.category)} · {f.file}:{f.line_start}–{f.line_end}
                    </span>
                  </button>
                ))}
                {node && (
                  <div className="df-detail">
                    <h3>{node.label}</h3>
                    <p className="df-muted" translate="no">
                      {node.kind}
                      {node.file ? ` · ${node.file}` : ""}
                    </p>
                    <p>
                      {nodeFinding
                        ? "The chaos lab will attack this first. Why it breaks is yours to explain in the grill."
                        : "No findings in this component."}
                    </p>
                  </div>
                )}
                <button type="button" className="ui-btn ui-btn-primary" onClick={() => setStage("chaos")}>
                  Run the Attack
                </button>
              </aside>
            </div>
          )}

          {stage === "chaos" && (
            <div className="df-chaos">
              <div className="df-banner is-broke" aria-live="polite">
                <strong>
                  <DecryptedText text={baselineRun.verdict.toUpperCase()} animateOn="view" sequential speed={40} />
                </strong>
                {baselineRun.summary}
              </div>
              <div className="df-chart">
                <div className="df-legend">
                  <span className="lg-bad">p95 latency (ms)</span>
                  <span className="lg-rps">requests/s</span>
                </div>
                <LiveLoadChart run={baselineRun} metric="p95" height={240} showRps />
              </div>
              <dl className="fr-metrics df-metrics">
                {(
                  [
                    ["Requests/s", baseline.rps, ""],
                    ["p95", baseline.p95_ms, " ms"],
                    ["p99", baseline.p99_ms, " ms"],
                    ["Invariant violations", baseline.violations, ""],
                  ] as const
                ).map(([name, value, suffix]) => (
                  <LiquidGlass key={name}>
                    <dt>{name}</dt>
                    <dd className={name === "Invariant violations" ? "is-bad" : undefined}>
                      <NumberFlow value={value} suffix={suffix} />
                    </dd>
                  </LiquidGlass>
                ))}
              </dl>
              <details className="df-script">
                <summary>Generated attack · {baselineRun.detail}</summary>
                <p className="df-muted">{attackFunctions.rationale}</p>
                <pre translate="no">
                  {`async def setup(client):\n${attackFunctions.setup_body}\n\nasync def request(client, ctx):\n${attackFunctions.request_body}\n\nasync def check_invariant(client, ctx):\n${attackFunctions.invariant_body}`}
                </pre>
              </details>
              <div className="df-row">
                <button type="button" className="ui-btn ui-btn-primary" onClick={() => setStage("grill")}>
                  Explain the Failure
                </button>
              </div>
            </div>
          )}

          {stage === "grill" && (
            <div className="df-grill-grid">
              <div className="df-grill">
                <div className="df-q">
                  <span className="df-muted">
                    Question · <NumberFlow value={left} suffix=" s" /> left
                  </span>
                  <h2>{grillTurn.question}</h2>
                </div>
                <label className="df-answer">
                  <span>Your answer</span>
                  <textarea
                    name="answer"
                    rows={5}
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    placeholder="The balance is read before the await, and…"
                    disabled={grade !== null}
                  />
                </label>
                <div className="df-row">
                  <button type="button" className="ui-btn ui-btn-primary" onClick={submitAnswer} disabled={!answer.trim() || grade !== null}>
                    Submit Answer
                  </button>
                  {grade !== null && (
                    <button type="button" className="ui-btn" onClick={() => setStage("fix")}>
                      Go Fix It
                    </button>
                  )}
                </div>
                {grade !== null && (
                  <>
                    <ul className="df-points" aria-live="polite">
                      {POINTS.map((p, i) => (
                        <li key={p} className={grade.hits[i] ? "is-hit" : "is-miss"}>
                          <span>{grade.hits[i] ? "Hit" : "Missed"}</span>
                          {p}
                        </li>
                      ))}
                    </ul>
                    {grade.hits.includes(false) && <p className="df-follow">{finding.grill.follow_up}</p>}
                    <div className="df-reveal">
                      <span className="df-muted">Finding revealed</span>
                      <p>{finding.explanation}</p>
                    </div>
                  </>
                )}
              </div>
              <div className="df-circle">
                <div className="df-circle-head">
                  <span className="df-muted">
                    {circled
                      ? `You circled ${audit.nodes.find((n) => n.id === circled)?.label}`
                      : "Point at it: circle the part that broke"}
                  </span>
                  <button
                    type="button"
                    className="ui-btn"
                    aria-pressed={pen}
                    onClick={() => setPen((p) => !p)}
                    disabled={grade !== null}
                  >
                    {pen ? "Done Drawing" : "Circle It"}
                  </button>
                </div>
                <div className="df-topo df-topo-grill" ref={topoHost}>
                  <TopologyView nodes={audit.nodes} edges={audit.edges} flags={FLAGS} pulseId={circled} />
                  {pen && (
                    <CirclePen
                      host={topoHost}
                      onCircle={(id) => {
                        setCircled(id);
                        setPen(false);
                        if (!id) toast.info("Nothing circled", { description: "Draw a loop around one box." });
                      }}
                    />
                  )}
                </div>
              </div>
            </div>
          )}

          {stage === "fix" && (
            <div className="df-fix">
              <div className="df-editor">
                <div className="df-tabs" role="tablist" aria-label="Project files">
                  {FILES.map((path) => (
                    <button
                      key={path}
                      type="button"
                      role="tab"
                      aria-selected={path === activeFile}
                      className={path === activeFile ? "is-on" : undefined}
                      onClick={() => openFile(path)}
                      translate="no"
                    >
                      {path}
                    </button>
                  ))}
                  <span className="rm-capture" title="Edit events sent by the capture library">
                    Capture · <NumberFlow value={captured} /> events
                  </span>
                </div>
                <div className="df-editor-host">
                  <CodeEditor
                    path={activeFile}
                    value={files[activeFile]}
                    onChange={(v) => setFiles((f) => ({ ...f, [activeFile]: v }))}
                    onEditor={onEditor}
                  />
                </div>
              </div>
              <aside className="df-side">
                <h2>{FIX.title}</h2>
                <p>{FIX.description}</p>
                {FIX.hints.slice(0, hintsShown).map((h) => (
                  <p key={h} className="df-follow">
                    {h}
                  </p>
                ))}
                <div className="df-row">
                  <button
                    type="button"
                    className="ui-btn"
                    onClick={() => setHintsShown((n) => Math.min(n + 1, FIX.hints.length))}
                    disabled={hintsShown >= FIX.hints.length}
                  >
                    Hint
                  </button>
                </div>
                <p className="df-muted">
                  Round {Math.min(rounds + 1, MAX_FIX_ROUNDS)} of {MAX_FIX_ROUNDS}: Verify re-runs the same attack on
                  your edited files.
                </p>
                <button type="button" className="ui-btn ui-btn-primary" onClick={verify} disabled={rounds >= MAX_FIX_ROUNDS}>
                  Verify the Fix
                </button>
              </aside>
            </div>
          )}

          {stage === "verify" && (
            <div className="df-chaos">
              {verified ? (
                <>
                  <div className={`df-banner ${verified.verdict === "held" ? "is-held" : "is-broke"}`} aria-live="polite">
                    <strong>
                      <DecryptedText key={verified.id + rounds} text={verified.verdict.toUpperCase()} animateOn="view" sequential speed={40} />
                    </strong>
                    {verified.summary}
                  </div>
                  <div className="df-chart">
                    <div className="df-legend">
                      <span className={verified.verdict === "held" ? "lg-ok" : "lg-bad"}>Invariant violations, verify</span>
                      <span className="lg-before">Baseline</span>
                    </div>
                    <LiveLoadChart key={verified.id + rounds} run={verified} compare={baselineRun} metric="violations" height={220} />
                  </div>
                  <dl className="fr-metrics df-metrics">
                    {(
                      [
                        ["Violations", baseline.violations, lastMetric(verified).violations, ""],
                        ["p95", baseline.p95_ms, lastMetric(verified).p95_ms, " ms"],
                        ["p99", baseline.p99_ms, lastMetric(verified).p99_ms, " ms"],
                      ] as const
                    ).map(([name, before, after, suffix]) => (
                      <LiquidGlass key={name}>
                        <dt>{name}, before → after</dt>
                        <dd className={name === "Violations" ? (after === 0 ? "is-ok" : "is-bad") : undefined}>
                          {before}
                          {suffix} → <NumberFlow value={after} suffix={suffix} />
                        </dd>
                      </LiquidGlass>
                    ))}
                  </dl>
                  <div className="df-row">
                    {verified.verdict === "held" ? (
                      <button type="button" className="ui-btn ui-btn-primary" onClick={() => setStage("verdict")}>
                        See the Verdict
                      </button>
                    ) : rounds < MAX_FIX_ROUNDS ? (
                      <button type="button" className="ui-btn ui-btn-primary" onClick={() => setStage("fix")}>
                        Back to Fix ({MAX_FIX_ROUNDS - rounds} {MAX_FIX_ROUNDS - rounds === 1 ? "round" : "rounds"} left)
                      </button>
                    ) : (
                      <button type="button" className="ui-btn ui-btn-primary" onClick={() => setStage("verdict")}>
                        See the Verdict
                      </button>
                    )}
                  </div>
                </>
              ) : (
                <div className="df-empty">
                  <p>Nothing to verify yet. Fix the code, then Verify re-runs the baseline attack on it.</p>
                  <button type="button" className="ui-btn ui-btn-primary" onClick={() => setStage("fix")}>
                    Go to Fix
                  </button>
                </div>
              )}
            </div>
          )}

          {stage === "verdict" && (
            <div className="df-verdict">
              <div className="df-gate-row">
                <div className={`df-gate ${passed ? "is-pass" : "is-fail"}`}>
                  <span className="df-muted">Merge gate</span>
                  <strong>{passed ? "PASS" : "FAIL"}</strong>
                </div>
                {/* the merge-gate card's numbers (PLAN §11.8); the image background is P2 */}
                <figure className="df-card" aria-label="Merge-gate card">
                  <span className="df-card-app" translate="no">
                    {project.name}
                  </span>
                  <span>
                    Violations {baseline.violations} → {verified ? lastMetric(verified).violations : "?"}
                  </span>
                  <span>
                    p99 {baseline.p99_ms} → {verified ? lastMetric(verified).p99_ms : "?"} ms
                  </span>
                  <strong className={passed ? "is-pass" : "is-fail"}>{passed ? "PASS" : "FAIL"}</strong>
                </figure>
              </div>
              <ul className="df-reasons">
                {(
                  [
                    [
                      verified
                        ? `${finding.id} ${verified.verdict === "held" ? "fixed" : "still broke"}: violations ${baseline.violations} → ${lastMetric(verified).violations}`
                        : `${finding.id} not verified yet`,
                      verified?.verdict === "held",
                    ],
                    [`Average grill score ≥ ${PASS_SCORE} (${grade ? grade.score : "not answered"})`, (grade?.score ?? 0) >= PASS_SCORE],
                    ["Root cause named for every finding", !!grade?.rootCause],
                  ] as const
                ).map(([text, met]) => (
                  <li key={text} className={met ? "is-hit" : "is-miss"}>
                    <span>{met ? "Met" : "Not met"}</span>
                    {text}
                  </li>
                ))}
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
