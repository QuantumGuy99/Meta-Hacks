"use client";

import NumberFlow, { NumberFlowGroup } from "@number-flow/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Streamdown } from "streamdown";
import { toast } from "sonner";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { api, errorText } from "@/lib/api";
import { attachEditorCapture, type EditorCapture } from "@/lib/capture/editor";
import { levelLabel } from "@/lib/fixtures";
import { codeAt } from "@/lib/replay";
import {
  CODE_MAX,
  feedMessages,
  isFinished,
  liveCaption,
  socketErrorText,
  statusLine,
  useClock,
  useLiveSession,
  useRemaining,
} from "@/lib/session";
import type { Phase, ProblemPublic } from "@/types/contracts";
import { CodeEditor } from "./CodeEditor";
import { InterviewerPanel } from "./InterviewerPanel";
import { MicControls } from "./MicControls";
import { NotesPanel } from "./NotesPanel";
import { TestPanel } from "./TestPanel";
import { UnderTheHood } from "./UnderTheHood";
import { useMic } from "./useMic";
import { useVoice } from "./useVoice";
import { VoiceControls, VoiceHint } from "./VoiceControls";

// The live coding room (/coding/[id], PLAN §14.2): everything on screen comes from the session socket.
// Edits go out through the capture lib; Run/Submit, Ask, Hint and the phase buttons are ClientMessages.

const FILE = "solution.py";
const PHASES: [Phase, string][] = [
  ["intro", "Warm-up"],
  ["clarify", "Clarify"],
  ["coding", "Coding"],
  ["wrap_up", "Wrap up"],
];
const PHASE_INDEX: Partial<Record<Phase, number>> = {
  setup: 0,
  intro: 0,
  clarify: 1,
  coding: 2,
  wrap_up: 3,
  ended: 4,
  reporting: 4,
  reported: 4,
  failed: 4,
};
// Edit kinds that change the code; focus and visibility events don't (#47).
const CODE_EVENTS = new Set(["change", "paste", "undo", "redo"]);
const RUN_TIMEOUT_MS = 90_000;
// A bad_phase error this soon after Skip Intro is a server without #57 refusing it: the warm-up just carries on.
const SKIP_REFUSAL_MS = 5_000;

type Editor = Parameters<NonNullable<Parameters<typeof CodeEditor>[0]["onEditor"]>>[0];

function problemMarkdown(p: ProblemPublic) {
  return [
    p.statement_md,
    p.examples.length ? "**Examples**" : "",
    ...p.examples.map((e) => `- \`${e.input}\` → \`${e.output}\`${e.explanation ? `: ${e.explanation}` : ""}`),
    p.constraints.length ? "**Constraints**" : "",
    ...p.constraints.map((c) => `- \`${c}\``),
  ]
    .filter(Boolean)
    .join("\n\n");
}

export function LiveRoom({ id }: { id: string }) {
  const router = useRouter();
  const { state, send, streamDone } = useLiveSession(id);
  const remaining = useRemaining(state);
  const caption = liveCaption(state);
  const { mic, toggleMic, setAsking, setPaused } = useMic(id);
  const voice = useVoice(state, setPaused);
  const [problem, setProblem] = useState<ProblemPublic | null>(null);
  const [code, setCode] = useState<string | null>(null);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [pending, setPending] = useState<{ kind: "run" | "submit"; runs: number; at: number; wall: number } | null>(null);
  const [showNotes, setShowNotes] = useState(false);
  const [ending, setEnding] = useState(false);
  const [skipped, setSkipped] = useState(false);
  const skippedAt = useRef<number | null>(null);
  const capture = useRef<EditorCapture | null>(null);

  const slug = state.session?.problem_slug ?? null;
  const phase = state.phase;
  // ended, reporting, reported or failed: the backend moves through all of them in a moment (#47)
  const ended = isFinished(phase);
  // code can only run from clarify on (the server rejects it during setup and the intro)
  const beforeClarify = phase === null || phase === "setup" || phase === "intro";
  // The warm-up comes before the problem (#57), so the problem and the editor wait for it to end.
  const warmingUp = phase === "setup" || phase === "intro";

  // The problem, then the code: the latest snapshot on the timeline (after a reload) or the starter code.
  useEffect(() => {
    if (!slug) return;
    let live = true;
    api
      .problem(slug)
      .then(async (p) => {
        const timeline = await api.timeline(id).catch(() => []);
        if (!live) return;
        // Only snapshots and real edits count: a focus or tab switch before any snapshot would rebuild "" (#47).
        const touched = timeline.some(
          (e) =>
            e.payload.file === FILE &&
            (e.kind === "snapshot" || (e.kind === "editor" && CODE_EVENTS.has(String(e.payload.kind)))),
        );
        setProblem(p);
        setCode(touched ? codeAt(timeline, FILE, Number.MAX_SAFE_INTEGER) : p.starter_code);
      })
      .catch((err) => live && toast.error("Couldn't load the problem", { description: errorText(err) }));
    return () => {
      live = false;
    };
  }, [slug, id]);

  // Edits are timed from the session's start, so attach the capture lib once both exist.
  const startedAtMs = state.session?.started_at ? Date.parse(state.session.started_at) : null;
  useEffect(() => {
    if (!editor || startedAtMs === null) return;
    const c = attachEditorCapture(editor, send, { startedAtMs, file: FILE });
    capture.current = c;
    return () => {
      c.dispose();
      if (capture.current === c) capture.current = null;
    };
  }, [editor, startedAtMs, send]);

  // Problems with a run as toasts (the Tests panel shows every result, so a pass needs none, #47): only for
  // results that arrive while you're here, not ones a reload brings back from the timeline.
  const lastRun = state.runs.at(-1) ?? null;
  const lastRunIsLive = lastRun ? `run:${lastRun.run_id}` in state.arrived : false;
  useEffect(() => {
    if (!lastRun || !lastRunIsLive) return;
    const id = `run-${lastRun.run_id}`;
    if (lastRun.compile_error) toast.error("Your code didn't run", { id, description: lastRun.compile_error.split("\n")[0] });
    else if (lastRun.passed < lastRun.total) toast.error(`${lastRun.total - lastRun.passed} of ${lastRun.total} tests failed`, { id });
  }, [lastRun, lastRunIsLive]);
  useEffect(() => {
    if (!state.error) return;
    const skip = skippedAt.current;
    if (state.error.code === "bad_phase" && skip !== null && state.error.at - skip < SKIP_REFUSAL_MS) return;
    toast.error(socketErrorText(state.error), { id: `err-${state.error.at}` });
  }, [state.error]);

  // When the interview ends (time, wrap-up or End), the report is next.
  useEffect(() => {
    if (!ended) return;
    const t = window.setTimeout(() => router.push(`/report/${id}`), 1500);
    return () => window.clearTimeout(t);
  }, [ended, id, router]);

  // A run is in flight until its result or an error arrives. If neither comes (a dropped connection), the
  // buttons come back after RUN_TIMEOUT_MS instead of staying disabled for good.
  const waiting = pending !== null && state.runs.length === pending.runs && !(state.error && state.error.at > pending.at);
  const now = useClock(waiting);
  const runTimedOut = waiting && now > 0 && now - pending.wall > RUN_TIMEOUT_MS;
  const running = waiting && !runTimedOut;
  const busy = running ? pending.kind : null;
  useEffect(() => {
    if (runTimedOut) toast.error("No result from the runner yet", { description: "Check your connection, then run again." });
  }, [runTimedOut]);
  // A submit that passes every test moves on to the wrap-up, so Submit locks; after a failing one it stays (#47).
  const submitted = state.runs.some((r) => r.kind === "submit" && r.total > 0 && r.passed === r.total && !r.compile_error);

  const run = (kind: "run" | "submit") => {
    if (running || !editor || beforeClarify || (kind === "submit" && submitted)) return;
    if (editor.getValue().length > CODE_MAX) {
      toast.error("Your code is too long to run", { description: `Keep it under ${CODE_MAX.toLocaleString()} characters.` });
      return;
    }
    capture.current?.snapshot(); // the backend must see the exact code being run
    setPending({ kind, runs: state.runs.length, at: performance.now(), wall: Date.now() });
    send({ type: kind === "run" ? "code.run" : "code.submit", file: FILE, code: editor.getValue() });
  };

  const reset = () => {
    if (!editor || !problem) return;
    if (capture.current) capture.current.programmatic(() => editor.setValue(problem.starter_code));
    else editor.setValue(problem.starter_code);
  };

  const end = async () => {
    setEnding(true);
    try {
      await api.endSession(id);
      router.push(`/report/${id}`);
    } catch (err) {
      toast.error("Couldn't end the interview", { description: errorText(err) });
      setEnding(false);
    }
  };

  // Skip Intro: straight to the problem, with the interviewer stopped mid-sentence. The button goes once pressed;
  // a server that refuses it just carries on.
  const skipIntro = () => {
    voice.interrupt();
    skippedAt.current = performance.now();
    setSkipped(true);
    send({ type: "phase.advance", to: "clarify" });
  };
  const showSkip = phase === "intro" && !skipped;

  const onEditor = useCallback((ed: Editor) => setEditor(ed), []);

  const mins = remaining === null ? null : Math.floor(remaining / 60);
  const secs = remaining === null ? null : remaining % 60;
  const status = statusLine(state.status);
  const step = phase ? (PHASE_INDEX[phase] ?? 0) : 0;
  const feedback = state.session?.config.feedback ?? "active";

  return (
    <div className="rm" data-ui>
      <header className="rm-top">
        <Link href="/" className="rm-brand" translate="no">
          Ares
        </Link>
        <ol className="room-phases" aria-label="Interview phase">
          {PHASES.map(([p, name], i) => (
            <li key={p} aria-current={i === step ? "step" : undefined} className={i < step ? "is-done" : undefined}>
              {name}
            </li>
          ))}
        </ol>
        <span className="room-badge">{levelLabel(feedback)} feedback</span>
        {status && (
          <span className="live-status" role="status">
            {status}
          </span>
        )}
        {mins !== null && secs !== null && !ended && (
          <span className="rm-timer" aria-label={`${mins} minutes ${secs} seconds left`}>
            <NumberFlowGroup>
              <NumberFlow value={mins} format={{ minimumIntegerDigits: 2 }} />
              <NumberFlow value={secs} format={{ minimumIntegerDigits: 2 }} prefix=":" digits={{ 1: { max: 5 } }} />
            </NumberFlowGroup>
          </span>
        )}
        <VoiceControls voice={voice} />
        <button type="button" className="ui-btn" aria-pressed={showNotes} onClick={() => setShowNotes((v) => !v)}>
          Notes
        </button>
        {showSkip && (
          <button type="button" className="ui-btn" onClick={skipIntro}>
            Skip Intro
          </button>
        )}
        {(phase === "clarify" || beforeClarify) && !showSkip && (
          // the server only takes clarify → coding, so the button waits out the intro
          <button
            type="button"
            className="ui-btn ui-btn-primary"
            onClick={() => send({ type: "phase.advance", to: "coding" })}
            disabled={beforeClarify}
            title={beforeClarify ? "Available once the interviewer has introduced the problem" : undefined}
          >
            Start Coding
          </button>
        )}
        {phase === "coding" && (
          <button type="button" className="ui-btn ui-btn-primary" onClick={() => send({ type: "phase.advance", to: "wrap_up" })}>
            I&apos;m Done
          </button>
        )}
        {ended ? (
          <Link href={`/report/${id}`} className="ui-btn ui-btn-primary">
            See Report
          </Link>
        ) : (
          <button type="button" className="ui-btn" onClick={end} disabled={ending || !state.session}>
            {ending ? "Ending…" : "End"}
          </button>
        )}
      </header>
      <VoiceHint voice={voice} />

      <ResizablePanelGroup orientation="horizontal" className="rm-body">
        <ResizablePanel defaultSize="26%" minSize="18%">
          <section className="rm-panel rm-problem" aria-label="Problem">
            <header className="rm-panel-head">
              <span>{warmingUp ? "Warm-up" : (problem?.title ?? "Loading the problem…")}</span>
              {problem && !warmingUp && (
                <span className="rm-tag">
                  {levelLabel(problem.difficulty)} · {problem.topics.map(levelLabel).join(", ")}
                </span>
              )}
            </header>
            {warmingUp ? (
              <p className="live-empty">
                A minute of getting to know you first. The problem appears here once the interviewer presents it, or now
                with Skip Intro.
              </p>
            ) : (
              problem && (
                <Streamdown className="rm-md" mode="static" controls={false}>
                  {problemMarkdown(problem)}
                </Streamdown>
              )
            )}
          </section>
        </ResizablePanel>
        <ResizableHandle />
        <ResizablePanel defaultSize="48%" minSize="30%">
          <ResizablePanelGroup orientation="vertical">
            <ResizablePanel defaultSize="68%" minSize="30%">
              <section className="rm-panel rm-editor" aria-label="Editor">
                <header className="rm-panel-head">
                  <span translate="no">{FILE}</span>
                  <span className="rm-actions">
                    <button type="button" className="ui-btn" onClick={reset} disabled={!editor || ended}>
                      Reset Code
                    </button>
                    <button type="button" className="ui-btn" onClick={() => run("run")} disabled={running || !editor || ended || beforeClarify}>
                      {busy === "run" ? "Running…" : "Run"}
                    </button>
                    <button
                      type="button"
                      className="ui-btn ui-btn-primary"
                      onClick={() => run("submit")}
                      disabled={running || submitted || !editor || ended || beforeClarify}
                    >
                      {submitted ? "Submitted" : busy === "submit" ? "Submitting…" : "Submit"}
                    </button>
                  </span>
                </header>
                <div className="rm-editor-host">
                  {warmingUp ? (
                    <p className="live-empty">The editor opens with the problem.</p>
                  ) : code !== null ? (
                    <CodeEditor value={code} onChange={setCode} readOnly={ended} onRun={() => run("run")} onEditor={onEditor} path={FILE} />
                  ) : (
                    <p className="live-empty">Loading your editor…</p>
                  )}
                </div>
              </section>
            </ResizablePanel>
            <ResizableHandle />
            <ResizablePanel defaultSize="32%" minSize="15%">
              <TestPanel result={running ? null : lastRun} running={running} />
            </ResizablePanel>
          </ResizablePanelGroup>
        </ResizablePanel>
        <ResizableHandle />
        <ResizablePanel defaultSize="26%" minSize="20%">
          <InterviewerPanel
            messages={feedMessages(state)}
            state={voice.speaking ? "speaking" : state.interviewer}
            streamingId={state.streamingId}
            onStreamDone={streamDone}
            onAsk={(text) => send({ type: "chat.send", text })}
            onHint={() => send({ type: "hint.request" })}
            hintsLeft={ended ? 0 : 1}
            panel={showNotes ? <NotesPanel notes={state.notes} flags={state.flags} /> : null}
            caption={caption}
            extra={
              state.session?.config.voice ? (
                <MicControls
                  mic={mic}
                  onToggle={toggleMic}
                  onAsking={(holding) => {
                    if (holding) voice.interrupt(); // barge-in: the candidate wants the floor
                    setAsking(holding);
                  }}
                  disabled={ended}
                />
              ) : null
            }
          />
        </ResizablePanel>
      </ResizablePanelGroup>
      <UnderTheHood events={state.activity} />
    </div>
  );
}
