"use client";

import NumberFlow from "@number-flow/react";
import { AnimatePresence, m } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { CodeEditor } from "@/components/room/CodeEditor";
import { InterviewerPanel } from "@/components/room/InterviewerPanel";
import { MicControls } from "@/components/room/MicControls";
import { UnderTheHood } from "@/components/room/UnderTheHood";
import { useMic } from "@/components/room/useMic";
import { api, errorText } from "@/lib/api";
import { attachEditorCapture, type EditorCapture } from "@/lib/capture/editor";
import { clock, levelLabel, severityLabel } from "@/lib/fixtures";
import {
  CHAT_MAX,
  CODE_MAX,
  socketErrorText,
  feedMessages,
  isFinished,
  liveCaption,
  statusLine,
  useClock,
  useLiveSession,
  useRemaining,
  VERIFY_MAX_FILES,
  type LiveState,
} from "@/lib/session";
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
const GRILL_WINDOW_MS = 90_000;
const VERIFY_TIMEOUT_MS = 180_000;

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
  // The finding whose file is open under the topology (the audit's file preview, PLAN §14.4).
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  // Date.now() of the last answer sent, to tell "grading" from "a follow-up question came back"
  const [answeredAt, setAnsweredAt] = useState<number | null>(null);
  const [files, setFiles] = useState<Record<string, string> | null>(null);
  const [original, setOriginal] = useState<Record<string, string>>({});
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [verifying, setVerifying] = useState<{ runs: number; at: number; wall: number } | null>(null);
  const capture = useRef<EditorCapture | null>(null);
  const [endingAt, setEndingAt] = useState<number | null>(null); // performance.now() of the End click
  const router = useRouter();

  const phase = state.phase;
  const audit = state.audit;
  // Follow the server's stage unless the candidate went back to look at an earlier one.
  const finished = isFinished(phase); // ended, reporting, reported or failed (#47)
  // End goes to the report once the server has ended the session, as in the coding room. A session that ends
  // on its own stays on its verdict, with See Report.
  const ending = endingAt !== null && !(state.error && state.error.at > endingAt); // an error gives End back
  useEffect(() => {
    if (ending && finished) router.push(`/report/${id}`);
  }, [ending, finished, id, router]);
  const current: Phase = finished ? "verdict" : phase && ORDER.includes(phase) ? phase : "audit";
  const view = picked && picked.at === phase ? picked.stage : current;
  const reached = ORDER.indexOf(current);

  // Memoised: the charts rebuild whenever they get a new run object.
  const { metrics, chaosRuns } = state;
  const baseline = useMemo(() => currentRun({ metrics, chaosRuns, phase }, "baseline"), [metrics, chaosRuns, phase]);
  const verified = useMemo(() => currentRun({ metrics, chaosRuns, phase }, "verify"), [metrics, chaosRuns, phase]);
  // the server only re-runs a baseline attack that finished with an error (defense.run_chaos)
  const baselineErrored = state.chaosRuns.find((r) => r.kind === "baseline" && r.verdict === "error") ?? null;
  const brokenIds = state.chaosRuns.filter((r) => r.kind === "baseline" && r.verdict === "broke").map((r) => r.finding_id);
  const lastGrilled = state.grill.at(-1) ?? null;
  const targetId = lastGrilled?.turn.finding_id ?? brokenIds[0] ?? audit?.findings[0]?.id ?? null;
  // The full finding (fix steps, points, explanation) comes with the grill result; after a reload only the
  // audit's public fields (title, file, lines) are back until the report.
  const target = lastGrilled?.finding ?? null;
  const shownTarget = target ?? audit?.findings.find((f) => f.id === targetId) ?? null;
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
  const findingFile = shownTarget?.file ?? null;
  const preview = audit?.findings.find((f) => f.id === previewId) ?? null;
  const previewLines = useMemo(
    () =>
      preview
        ? Array.from({ length: preview.line_end - preview.line_start + 1 }, (_, i) => ({
            line: preview.line_start + i,
            note: `Flagged by the audit: ${preview.title}`,
          }))
        : [],
    [preview],
  );
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

  // The 90 s answer window (PLAN §11.5), from when the current question reached this browser until it's
  // graded. A question loaded from the timeline after a reload falls back to the session's clock.
  const askedAt = asked ? (state.arrived[asked.id] ?? (startedAtMs !== null ? startedAtMs + asked.t : null)) : null;
  const deadline = phase === "grill" && !grilled && askedAt !== null ? askedAt + GRILL_WINDOW_MS : null;

  // Long server-side waits get a running clock: the audit (about a minute with the real models, issue #35)
  // counts from the session's start, writing the attack from when the audit arrived.
  const auditWait = !audit && (phase === "setup" || phase === "audit");
  const attackWait = phase === "chaos" && !baseline;
  const verifyWaiting =
    verifying !== null && state.chaosRuns.length === verifying.runs && !(state.error && state.error.at > verifying.at);
  const now = useClock(deadline !== null || auditWait || attackWait || verifyWaiting);
  const answerLeft = deadline === null || now === 0 ? null : Math.max(0, Math.ceil((deadline - now) / 1000));
  const waited = (from: number | null | undefined) => (from && now ? clock(Math.max(0, (now - from) / 1000)) : null);
  const auditWaited = auditWait ? waited(startedAtMs) : null;
  const attackWaited = attackWait ? waited(state.arrived.audit) : null;

  useEffect(() => {
    if (state.error) toast.error(socketErrorText(state.error), { id: `err-${state.error.at}` });
  }, [state.error]);
  // Attack results as toasts: only ones that finish while you're here, not ones a reload brings back.
  const lastDone = state.chaosRuns.at(-1);
  const lastDoneIsLive = lastDone ? `chaos:${lastDone.id}` in state.arrived : false;
  useEffect(() => {
    if (!lastDone || !lastDoneIsLive) return;
    toast[lastDone.verdict === "held" ? "success" : lastDone.verdict === "broke" ? "error" : "warning"](
      `${lastDone.kind === "verify" ? "Verify" : "Attack"}: ${lastDone.verdict}`,
      { id: `chaos-${lastDone.id}`, description: lastDone.summary },
    );
  }, [lastDone, lastDoneIsLive]);

  // Verify is in flight until its attack finishes or an error arrives; if neither comes (a dropped
  // connection), the button comes back after VERIFY_TIMEOUT_MS instead of staying disabled for good.
  const verifyTimedOut = verifyWaiting && now > 0 && now - verifying.wall > VERIFY_TIMEOUT_MS;
  const running = verifyWaiting && !verifyTimedOut;
  useEffect(() => {
    if (verifyTimedOut) toast.error("No result from Verify yet", { description: "Check your connection, then verify again." });
  }, [verifyTimedOut]);
  const verify = () => {
    if (!targetId || !files || running) return;
    capture.current?.snapshot();
    // Only the edited files (the server takes at most VERIFY_MAX_FILES, each under CODE_MAX); with no edits,
    // the flagged file, so Verify still re-runs the attack.
    const changed = Object.fromEntries(Object.entries(files).filter(([p, code]) => original[p] !== code));
    const sent = Object.keys(changed).length
      ? changed
      : findingFile && files[findingFile] !== undefined
        ? { [findingFile]: files[findingFile] }
        : {};
    if (Object.keys(sent).length === 0) {
      toast.error("Nothing to verify yet", { description: "Edit the flagged file, then verify." });
      return;
    }
    if (Object.keys(sent).length > VERIFY_MAX_FILES || Object.values(sent).some((code) => code.length > CODE_MAX)) {
      toast.error("Too much to verify at once", {
        description: `Verify takes up to ${VERIFY_MAX_FILES} edited files of under ${CODE_MAX.toLocaleString()} characters each.`,
      });
      return;
    }
    setVerifying({ runs: state.chaosRuns.length, at: performance.now(), wall: Date.now() });
    send({ type: "defense.verify", finding_id: targetId, files: sent });
  };

  const sendAnswer = () => {
    const text = answer.trim();
    if (!text) return;
    send({ type: "chat.send", text });
    setAnswer("");
    setAnsweredAt(Date.now());
  };
  // The grade (defense.grill.eval) only comes once the grill for a finding is final, after a follow-up if one
  // is asked (#29). Until then a newer question means a follow-up: the answer box comes back, not "grading".
  const grading = answeredAt !== null && !grilled && view === "grill" && (askedAt === null || answeredAt > askedAt);

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
        {remaining !== null && !finished && (
          <span className="rm-timer" aria-label={`${Math.floor(remaining / 60)} minutes left`}>
            {Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, "0")}
          </span>
        )}
        {finished ? (
          <Link href={`/report/${id}`} className="ui-btn ui-btn-primary">
            See Report
          </Link>
        ) : (
          <button
            type="button"
            className="ui-btn"
            onClick={() => {
              setEndingAt(performance.now());
              send({ type: "session.end" });
            }}
            disabled={!state.session || ending}
          >
            {ending ? "Ending…" : "End"}
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
                  <div className="live-audit-main">
                    <div className="df-topo">
                      <TopologyView
                        nodes={audit.nodes}
                        edges={audit.edges}
                        selectedId={selected}
                        onSelect={(nodeId) => {
                          setSelected(nodeId);
                          setPreviewId(audit.findings.find((f) => f.node_id === nodeId)?.id ?? null);
                        }}
                        flags={flags}
                        pulseId={state.highlight?.node_id ?? null}
                      />
                    </div>
                    {preview && (
                      <section className="live-preview" aria-label={`Preview of ${preview.file}`}>
                        <header className="rm-panel-head">
                          <span translate="no">
                            {preview.file} · lines {preview.line_start}–{preview.line_end}
                          </span>
                          <button type="button" className="ui-btn" onClick={() => setPreviewId(null)}>
                            Close
                          </button>
                        </header>
                        {original[preview.file] !== undefined ? (
                          <CodeEditor
                            key={preview.id}
                            path={`preview/${preview.file}`}
                            value={original[preview.file]}
                            readOnly
                            flagged={previewLines}
                            onEditor={(ed) => ed.revealLinesInCenter(preview.line_start, preview.line_end)}
                          />
                        ) : (
                          <p className="live-empty">{files ? "This file isn't part of the project's source." : "Loading the file…"}</p>
                        )}
                      </section>
                    )}
                  </div>
                  <aside className="df-side">
                    <h2>Findings</h2>
                    <p className="df-muted">{audit.summary}</p>
                    {audit.findings.map((f) => (
                      <button
                        key={f.id}
                        type="button"
                        className={f.id === previewId ? "df-finding is-on" : "df-finding"}
                        aria-pressed={f.id === previewId}
                        onClick={() => {
                          setSelected(f.node_id);
                          setPreviewId(f.id);
                        }}
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
                  <p className="df-muted" aria-live="off">
                    {auditWaited ? `${auditWaited} so far. ` : ""}The first audit of a project takes about a minute.
                  </p>
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
                            ? `Writing the attack and starting the app in the sandbox…${attackWaited ? ` ${attackWaited}` : ""}`
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
                  <span className="df-muted" aria-live="off">
                    Question
                    {answerLeft !== null &&
                      (answerLeft > 0 ? (
                        <>
                          {" · "}
                          <NumberFlow value={answerLeft} suffix=" s" /> left to answer
                        </>
                      ) : (
                        " · Time's up: answer now"
                      ))}
                  </span>
                  <h2>{question?.text ?? "The question arrives once the attack finishes."}</h2>
                </div>
                {!grilled && (
                  <>
                    <label className="df-answer">
                      <span>Your answer</span>
                      <textarea
                        name="answer"
                        rows={5}
                        maxLength={CHAT_MAX}
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
                    {grilled.finding ? (
                      <>
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
                    ) : (
                      <p className="df-muted">
                        You hit {grilled.turn.eval.points_hit.length} of{" "}
                        {grilled.turn.eval.points_hit.length + grilled.turn.eval.points_missed.length} points. Each point
                        and the full explanation are in your report.
                      </p>
                    )}
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
                        readOnly={phase === "verdict" || finished}
                      />
                    ) : (
                      <p className="live-empty">Loading the project&apos;s files…</p>
                    )}
                  </div>
                </div>
                <aside className="df-side">
                  <h2>{shownTarget?.title ?? "Fix what broke"}</h2>
                  {shownTarget && (
                    <p className="df-muted" translate="no">
                      {shownTarget.file}:{shownTarget.line_start}–{shownTarget.line_end}
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
              <MicControls mic={mic} onToggle={toggleMic} onAsking={setAsking} disabled={finished} />
            ) : null
          }
        />
      </div>
      <UnderTheHood events={state.activity} />
    </div>
  );
}
