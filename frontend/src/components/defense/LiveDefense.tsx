"use client";

import NumberFlow from "@number-flow/react";
import { AnimatePresence, m } from "motion/react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { CodeEditor } from "@/components/room/CodeEditor";
import { InterviewerPanel } from "@/components/room/InterviewerPanel";
import { MicControls } from "@/components/room/MicControls";
import { useMic } from "@/components/room/useMic";
import { api, errorText } from "@/lib/api";
import { attachEditorCapture, type EditorCapture } from "@/lib/capture/editor";
import { levelLabel, severityLabel } from "@/lib/fixtures";
import { feedMessages, liveCaption, statusLine, useLiveSession, useRemaining, type LiveState } from "@/lib/session";
import type { ChaosMetric, ChaosRun, Phase } from "@/types/contracts";
import { LiveLoadChart } from "./LiveLoadChart";
import { TopologyView } from "./TopologyView";

// The live Project Defense (/defense/[id], PLAN §11, §14.4). The server drives the stages: audit → chaos →
// grill → fix → verify → verdict. The grill answer goes out as chat; Verify sends the edited files.

const STAGES: [Phase, string][] = [
  ["audit", "Audit"],
  ["chaos", "Chaos"],
  ["grill", "Grill"],
  ["fix", "Fix"],
  ["verify", "Verify"],
  ["verdict", "Verdict"],
];
const ORDER = STAGES.map(([p]) => p);

type Editor = Parameters<NonNullable<Parameters<typeof CodeEditor>[0]["onEditor"]>>[0];

const last = (run: ChaosRun | null): ChaosMetric | null => run?.metrics.at(-1) ?? null;

/** The run in progress, drawn from its metrics before defense.chaos.done arrives; else the newest finished one. */
function currentRun(
  { metrics, chaosRuns, phase }: Pick<LiveState, "metrics" | "chaosRuns" | "phase">,
  kind: ChaosRun["kind"],
): ChaosRun | null {
  const doneIds = new Set(chaosRuns.map((r) => r.id));
  const liveId = metrics.findLast((x) => !doneIds.has(x.run_id))?.run_id;
  if (liveId && phase === (kind === "verify" ? "verify" : "chaos")) {
    const samples = metrics.filter((x) => x.run_id === liveId);
    return { id: liveId, finding_id: "", kind, attempt: 0, script: "", verdict: "held", summary: "", detail: "", metrics: samples };
  }
  return chaosRuns.filter((r) => r.kind === kind).at(-1) ?? null;
}

export function LiveDefense({ id }: { id: string }) {
  const { state, send, streamDone } = useLiveSession(id);
  const remaining = useRemaining(state);
  const caption = liveCaption(state);
  const { mic, toggleMic, setAsking } = useMic(id);
  const [picked, setPicked] = useState<{ stage: Phase; at: Phase | null } | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [answeredAt, setAnsweredAt] = useState<number | null>(null);
  const [files, setFiles] = useState<Record<string, string> | null>(null);
  const [original, setOriginal] = useState<Record<string, string>>({});
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [verifying, setVerifying] = useState<{ runs: number; at: number } | null>(null);
  const capture = useRef<EditorCapture | null>(null);

  const phase = state.phase;
  const audit = state.audit;
  // Follow the server's stage unless the candidate went back to look at an earlier one.
  const current: Phase = phase === "ended" ? "verdict" : phase && ORDER.includes(phase) ? phase : "audit";
  const view = picked && picked.at === phase ? picked.stage : current;
  const reached = ORDER.indexOf(current);

  // Memoised: the charts rebuild whenever they get a new run object.
  const { metrics, chaosRuns } = state;
  const baseline = useMemo(() => currentRun({ metrics, chaosRuns, phase }, "baseline"), [metrics, chaosRuns, phase]);
  const verified = useMemo(() => currentRun({ metrics, chaosRuns, phase }, "verify"), [metrics, chaosRuns, phase]);
  // the server only re-runs a baseline attack that finished with an error (defense.run_chaos)
  const baselineErrored = state.chaosRuns.find((r) => r.kind === "baseline" && r.verdict === "error") ?? null;
  const brokenIds = state.chaosRuns.filter((r) => r.kind === "baseline" && r.verdict === "broke").map((r) => r.finding_id);
  const target = state.grill.at(-1)?.finding ?? null;
  const targetId = target?.id ?? brokenIds[0] ?? audit?.findings[0]?.id ?? null;
  const flags = useMemo(
    () => Object.fromEntries((audit?.findings ?? []).filter((f) => f.node_id).map((f) => [f.node_id!, f.title])),
    [audit],
  );
  const grilled = state.grill.find((g) => g.turn.finding_id === targetId) ?? null;
  // Once graded, the turn carries its own question; before that it's the newest grill message (the fix
  // hand-off also comes in as a grill message, but only after grading).
  const asked = [...state.interventions].reverse().find((iv) => iv.trigger === "grill" && state.shown.includes(iv.id));
  const question = grilled ? { text: grilled.turn.question } : asked;

  // The project's files for the fix stage (samples only until uploads land).
  const projectId = state.session?.project_id ?? null;
  useEffect(() => {
    if (!projectId) return;
    let live = true;
    api
      .projectFiles(projectId)
      .then((src) => {
        if (!live) return;
        setFiles(src.files);
        setOriginal(src.files);
      })
      .catch((err) => live && toast.error("Couldn't load the project's files", { description: errorText(err) }));
    return () => {
      live = false;
    };
  }, [projectId]);
  const paths = useMemo(() => Object.keys(files ?? {}).sort(), [files]);
  const findingFile = target?.file ?? audit?.findings.find((f) => f.id === targetId)?.file ?? null;
  const openFile = activeFile ?? (findingFile && paths.includes(findingFile) ? findingFile : (paths[0] ?? null));

  const startedAtMs = state.session?.started_at ? Date.parse(state.session.started_at) : null;
  const firstFile = useRef(openFile);
  useEffect(() => {
    if (!editor || startedAtMs === null) return;
    const c = attachEditorCapture(editor, send, { startedAtMs, file: firstFile.current ?? undefined });
    capture.current = c;
    return () => {
      c.dispose();
      if (capture.current === c) capture.current = null;
    };
  }, [editor, startedAtMs, send]);
  useEffect(() => {
    firstFile.current = openFile;
    if (openFile) capture.current?.setFile(openFile);
  }, [openFile]);
  const onEditor = useCallback((ed: Editor) => setEditor(ed), []);

  useEffect(() => {
    if (state.error) toast.error(state.error.message, { id: `err-${state.error.at}` });
  }, [state.error]);
  const lastDone = state.chaosRuns.at(-1);
  useEffect(() => {
    if (!lastDone) return;
    toast[lastDone.verdict === "held" ? "success" : lastDone.verdict === "broke" ? "error" : "warning"](
      `${lastDone.kind === "verify" ? "Verify" : "Attack"}: ${lastDone.verdict}`,
      { description: lastDone.summary },
    );
  }, [lastDone]);

  const running = verifying !== null && state.chaosRuns.length === verifying.runs && !(state.error && state.error.at > verifying.at);
  const verify = () => {
    if (!targetId || !files || running) return;
    capture.current?.snapshot();
    const changed = Object.fromEntries(Object.entries(files).filter(([p, code]) => original[p] !== code));
    const sent = Object.keys(changed).length ? changed : findingFile && files[findingFile] ? { [findingFile]: files[findingFile] } : files;
    setVerifying({ runs: state.chaosRuns.length, at: performance.now() });
    send({ type: "defense.verify", finding_id: targetId, files: sent });
  };

  const sendAnswer = () => {
    const text = answer.trim();
    if (!text) return;
    send({ type: "chat.send", text });
    setAnswer("");
    setAnsweredAt(performance.now());
  };
  const grading = answeredAt !== null && !grilled && view === "grill";

  const status = statusLine(state.status);
  const metric = last(baseline);
  const after = last(verified);
  const verdict = state.verdict;

  return (
    <div className="df live-df" data-ui>
      <header className="rm-top">
        <Link href="/" className="rm-brand" translate="no">
          Ares
        </Link>
        <ol className="df-stages" aria-label="Defense stages">
          {STAGES.map(([p, name], i) => (
            <li key={p}>
              <button
                type="button"
                aria-current={p === view ? "step" : undefined}
                className={i < reached ? "is-done" : undefined}
                disabled={i > reached}
                onClick={() => setPicked({ stage: p, at: phase })}
              >
                {name}
              </button>
            </li>
          ))}
        </ol>
        {status && (
          <span className="live-status" role="status">
            {status}
          </span>
        )}
        <span className="room-badge" translate="no">
          {projectId ?? "Project"} · {levelLabel(state.session?.config.feedback ?? "active")} feedback
        </span>
        {remaining !== null && (
          <span className="rm-timer" aria-label={`${Math.floor(remaining / 60)} minutes left`}>
            {Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, "0")}
          </span>
        )}
        {phase === "ended" ? (
          <Link href={`/report/${id}`} className="ui-btn ui-btn-primary">
            See Report
          </Link>
        ) : (
          <button type="button" className="ui-btn" onClick={() => send({ type: "session.end" })} disabled={!state.session}>
            End
          </button>
        )}
      </header>

      <div className="live-df-body">
        <AnimatePresence mode="wait" initial={false}>
          <m.section
            key={view}
            className="df-stage"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            aria-label={`${view} stage`}
          >
            {/* a stage that failed on the server stays visible here, not only as a passing toast */}
            {state.error && view === current && (
              <div className="setup-error live-stage-error" role="alert">
                {state.error.message}
                {baselineErrored && (
                  <button
                    type="button"
                    className="ui-btn"
                    onClick={() => send({ type: "defense.run_chaos", finding_id: baselineErrored.finding_id })}
                  >
                    Run the Attack Again
                  </button>
                )}
              </div>
            )}
            {view === "audit" &&
              (audit ? (
                <div className="df-audit">
                  <div className="df-topo">
                    <TopologyView nodes={audit.nodes} edges={audit.edges} selectedId={selected} onSelect={setSelected} flags={flags} pulseId={state.highlight?.node_id ?? null} />
                  </div>
                  <aside className="df-side">
                    <h2>Findings</h2>
                    <p className="df-muted">{audit.summary}</p>
                    {audit.findings.map((f) => (
                      <button
                        key={f.id}
                        type="button"
                        className={f.node_id && f.node_id === selected ? "df-finding is-on" : "df-finding"}
                        onClick={() => setSelected(f.node_id)}
                      >
                        <span className="sev">{severityLabel(f.severity)}</span>
                        <strong>{f.title}</strong>
                        <span className="df-muted" translate="no">
                          {levelLabel(f.category.replace(/_/g, " "))} · {f.file}:{f.line_start}–{f.line_end}
                        </span>
                      </button>
                    ))}
                  </aside>
                </div>
              ) : (
                <div className="df-empty">
                  <p>Auditing the project: mapping its routes, services and stores, and looking for what could break.</p>
                </div>
              ))}

            {(view === "chaos" || view === "verify") && (
              <div className="df-chaos">
                {(() => {
                  const run = view === "chaos" ? baseline : verified;
                  if (!run) {
                    return (
                      <div className="df-empty">
                        <p>
                          {view === "chaos"
                            ? "Writing the attack and starting the app in the sandbox…"
                            : "Nothing verified yet. Fix the code, then Verify re-runs the same attack on it."}
                        </p>
                      </div>
                    );
                  }
                  const finished = state.chaosRuns.some((r) => r.id === run.id);
                  return (
                    <>
                      <div className={`df-banner ${!finished ? "" : run.verdict === "held" ? "is-held" : "is-broke"}`} aria-live="polite">
                        <strong>{finished ? run.verdict.toUpperCase() : "RUNNING"}</strong>
                        {finished ? run.summary : `${run.metrics.length} samples so far`}
                      </div>
                      <div className="df-chart">
                        <div className="df-legend">
                          {view === "chaos" ? (
                            <>
                              <span className="lg-bad">p95 latency (ms)</span>
                              <span className="lg-rps">requests/s</span>
                            </>
                          ) : (
                            <>
                              <span className={run.verdict === "held" ? "lg-ok" : "lg-bad"}>Invariant violations, verify</span>
                              <span className="lg-before">Baseline</span>
                            </>
                          )}
                        </div>
                        {view === "chaos" ? (
                          <LiveLoadChart key={run.id} run={run} metric="p95" height={240} showRps />
                        ) : (
                          <LiveLoadChart
                            key={run.id}
                            run={run}
                            compare={baseline ?? undefined}
                            metric="violations"
                            height={220}
                          />
                        )}
                      </div>
                      <dl className="fr-metrics df-metrics">
                        {(view === "chaos"
                          ? ([
                              ["Requests/s", metric?.rps ?? 0, ""],
                              ["p95", metric?.p95_ms ?? 0, " ms"],
                              ["p99", metric?.p99_ms ?? 0, " ms"],
                              ["Invariant violations", metric?.violations ?? 0, ""],
                            ] as const)
                          : ([
                              ["Violations", after?.violations ?? 0, ""],
                              ["p95", after?.p95_ms ?? 0, " ms"],
                              ["p99", after?.p99_ms ?? 0, " ms"],
                              ["Errors", after?.errors ?? 0, ""],
                            ] as const)
                        ).map(([name, value, suffix]) => (
                          <div key={name}>
                            <dt>{name}</dt>
                            <dd>
                              <NumberFlow value={Math.round(value)} suffix={suffix} />
                            </dd>
                          </div>
                        ))}
                      </dl>
                      {finished && run.script && (
                        <details className="df-script">
                          <summary>Generated attack · {run.detail}</summary>
                          <pre translate="no">{run.script}</pre>
                        </details>
                      )}
                    </>
                  );
                })()}
              </div>
            )}

            {view === "grill" && (
              <div className="df-grill">
                <div className="df-q">
                  <span className="df-muted">Question</span>
                  <h2>{question?.text ?? "The question arrives once the attack finishes."}</h2>
                </div>
                {!grilled && (
                  <>
                    <label className="df-answer">
                      <span>Your answer</span>
                      <textarea
                        name="answer"
                        rows={5}
                        value={answer}
                        onChange={(e) => setAnswer(e.target.value)}
                        placeholder="Explain what broke and why…"
                        disabled={!question || phase !== "grill"}
                      />
                    </label>
                    <div className="df-row">
                      <button type="button" className="ui-btn ui-btn-primary" onClick={sendAnswer} disabled={!answer.trim() || phase !== "grill"}>
                        Submit Answer
                      </button>
                      {grading && <span className="df-muted">Grading your answer…</span>}
                    </div>
                  </>
                )}
                {grilled && (
                  <>
                    <p>
                      Scored <strong>{grilled.turn.score}</strong> of 10. {grilled.turn.eval.feedback}
                    </p>
                    <ul className="df-points" aria-live="polite">
                      {grilled.finding.grill.expected_points.map((p, i) => {
                        const hit = grilled.turn.eval.points_hit.includes(i);
                        return (
                          <li key={p} className={hit ? "is-hit" : "is-miss"}>
                            <span>{hit ? "Hit" : "Missed"}</span>
                            {p}
                          </li>
                        );
                      })}
                    </ul>
                    <div className="df-reveal">
                      <span className="df-muted">Finding revealed</span>
                      <p>{grilled.finding.explanation}</p>
                    </div>
                  </>
                )}
              </div>
            )}

            {view === "fix" && (
              <div className="df-fix">
                <div className="df-editor">
                  <div className="df-tabs" role="tablist" aria-label="Project files">
                    {paths.map((path) => (
                      <button
                        key={path}
                        type="button"
                        role="tab"
                        aria-selected={path === openFile}
                        className={path === openFile ? "is-on" : undefined}
                        onClick={() => setActiveFile(path)}
                        translate="no"
                      >
                        {path}
                        {files && original[path] !== files[path] ? " •" : ""}
                      </button>
                    ))}
                  </div>
                  <div className="df-editor-host">
                    {files && openFile ? (
                      <CodeEditor
                        path={openFile}
                        value={files[openFile]}
                        onChange={(v) => setFiles((f) => (f ? { ...f, [openFile]: v } : f))}
                        onEditor={onEditor}
                        readOnly={phase === "verdict" || phase === "ended"}
                      />
                    ) : (
                      <p className="live-empty">Loading the project&apos;s files…</p>
                    )}
                  </div>
                </div>
                <aside className="df-side">
                  <h2>{target?.title ?? "Fix what broke"}</h2>
                  {target && (
                    <p className="df-muted" translate="no">
                      {target.file}:{target.line_start}–{target.line_end}
                    </p>
                  )}
                  {target?.fix_steps.map((s) => (
                    <p key={s.id}>
                      <strong>{s.title}.</strong> {s.description}
                    </p>
                  ))}
                  <p className="df-muted">Verify re-runs the same attack on your edited files.</p>
                  <button type="button" className="ui-btn ui-btn-primary" onClick={verify} disabled={running || !files || !targetId}>
                    {running ? "Verifying…" : "Verify the Fix"}
                  </button>
                </aside>
              </div>
            )}

            {view === "verdict" &&
              (verdict ? (
                <div className="df-verdict">
                  <div className="df-gate-row">
                    <div className={`df-gate ${verdict.passed ? "is-pass" : "is-fail"}`}>
                      <span className="df-muted">Merge gate</span>
                      <strong>{verdict.passed ? "PASS" : "FAIL"}</strong>
                    </div>
                    <figure className="df-card" aria-label="Merge-gate card">
                      <span className="df-card-app" translate="no">
                        {projectId}
                      </span>
                      <span>
                        Violations {metric?.violations ?? "?"} → {after?.violations ?? "?"}
                      </span>
                      <span>
                        p99 {metric?.p99_ms ?? "?"} → {after?.p99_ms ?? "?"} ms
                      </span>
                      <span>Grill average {verdict.avg_grill_score.toFixed(1)}</span>
                      <strong className={verdict.passed ? "is-pass" : "is-fail"}>{verdict.passed ? "PASS" : "FAIL"}</strong>
                    </figure>
                  </div>
                  <ul className="df-reasons">
                    {verdict.reasons.map((r) => (
                      <li key={r} className={verdict.passed ? "is-hit" : "is-miss"}>
                        <span>{verdict.passed ? "Met" : "Note"}</span>
                        {r}
                      </li>
                    ))}
                  </ul>
                  <Link href={`/report/${id}`} className="ui-btn ui-btn-primary">
                    Open the Report
                  </Link>
                </div>
              ) : (
                <div className="df-empty">
                  <p>The verdict comes after Verify.</p>
                </div>
              ))}
          </m.section>
        </AnimatePresence>

        <InterviewerPanel
          messages={feedMessages(state)}
          state={state.interviewer}
          streamingId={state.streamingId}
          onStreamDone={streamDone}
          onAsk={(text) => send({ type: "chat.send", text })}
          caption={caption}
          extra={
            state.session?.config.voice ? (
              <MicControls mic={mic} onToggle={toggleMic} onAsking={setAsking} disabled={phase === "ended"} />
            ) : null
          }
        />
      </div>
    </div>
  );
}
