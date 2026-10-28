"use client";

import NumberFlow, { NumberFlowGroup } from "@number-flow/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Streamdown } from "streamdown";
import { toast } from "sonner";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { api, errorText } from "@/lib/api";
import { attachEditorCapture, type EditorCapture } from "@/lib/capture/editor";
import { levelLabel } from "@/lib/fixtures";
import { codeAt } from "@/lib/replay";
import { feedMessages, liveCaption, statusLine, useLiveSession, useRemaining } from "@/lib/session";
import type { Phase, ProblemPublic } from "@/types/contracts";
import { CodeEditor } from "./CodeEditor";
import { InterviewerPanel, type RoomNote } from "./InterviewerPanel";
import { TestPanel } from "./TestPanel";
import { MIC_LABEL, useRoomVoice } from "./useRoomVoice";

// The live coding room (/coding/[id], PLAN §14.2): everything on screen comes from the session socket.
// Edits go out through the capture lib; Run/Submit, Ask, Hint and the phase buttons are ClientMessages.

const FILE = "solution.py";
const PHASES: [Phase, string][] = [
  ["clarify", "Clarify"],
  ["coding", "Coding"],
  ["wrap_up", "Wrap up"],
];
const PHASE_INDEX: Partial<Record<Phase, number>> = { setup: 0, intro: 0, clarify: 0, coding: 1, wrap_up: 2, ended: 3 };

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
  const { speaking, mic, toggleMic } = useRoomVoice(id, state, caption);
  const [problem, setProblem] = useState<ProblemPublic | null>(null);
  const [code, setCode] = useState<string | null>(null);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [pending, setPending] = useState<{ runs: number; at: number } | null>(null);
  const [showNotes, setShowNotes] = useState(false);
  const [ending, setEnding] = useState(false);
  const capture = useRef<EditorCapture | null>(null);

  const slug = state.session?.problem_slug ?? null;
  const phase = state.phase;
  const ended = phase === "ended";

  // The problem, then the code: the latest snapshot on the timeline (after a reload) or the starter code.
  useEffect(() => {
    if (!slug) return;
    let live = true;
    api
      .problem(slug)
      .then(async (p) => {
        const timeline = await api.timeline(id).catch(() => []);
        if (!live) return;
        const touched = timeline.some((e) => (e.kind === "snapshot" || e.kind === "editor") && e.payload.file === FILE);
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

  // Run results and errors as toasts.
  const lastRun = state.runs.at(-1) ?? null;
  useEffect(() => {
    if (!lastRun) return;
    if (lastRun.compile_error) toast.error("Your code didn't run", { description: lastRun.compile_error.split("\n")[0] });
    else if (lastRun.passed === lastRun.total) toast.success(`${lastRun.kind === "submit" ? "Submitted" : "Ran"}: all ${lastRun.total} tests passed`);
    else toast.error(`${lastRun.total - lastRun.passed} of ${lastRun.total} tests failed`);
  }, [lastRun]);
  useEffect(() => {
    if (state.error) toast.error(state.error.message, { id: `err-${state.error.at}` });
  }, [state.error]);

  // When the interview ends (time, wrap-up or End), the report is next.
  useEffect(() => {
    if (!ended) return;
    const t = window.setTimeout(() => router.push(`/report/${id}`), 1500);
    return () => window.clearTimeout(t);
  }, [ended, id, router]);

  const running = pending !== null && state.runs.length === pending.runs && !(state.error && state.error.at > pending.at);

  const run = (kind: "run" | "submit") => {
    if (running || !editor) return;
    capture.current?.snapshot(); // the backend must see the exact code being run
    setPending({ runs: state.runs.length, at: performance.now() });
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

  const onEditor = useCallback((ed: Editor) => setEditor(ed), []);

  const notes: RoomNote[] = useMemo(
    () => [
      ...(state.notes?.steps ?? []).map((s, i) => ({
        title: `Step ${i + 1}${s.evidence ? `: ${s.evidence}` : ""}`,
        status: s.status,
        evidence: s.evidence,
      })),
      ...(state.notes?.issues ?? []).map((issue) => ({
        title: `${issue.line ? `Line ${issue.line}: ` : ""}${issue.description}`,
        status: "noted" as const,
      })),
      // integrity notes are facts, never accusations (PLAN §4.4 rule 6)
      ...state.flags.map((f) => ({ title: f.detail.charAt(0).toUpperCase() + f.detail.slice(1), status: "noted" as const })),
    ],
    [state.notes, state.flags],
  );

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
        {mins !== null && secs !== null && (
          <span className="rm-timer" aria-label={`${mins} minutes ${secs} seconds left`}>
            <NumberFlowGroup>
              <NumberFlow value={mins} format={{ minimumIntegerDigits: 2 }} />
              <NumberFlow value={secs} format={{ minimumIntegerDigits: 2 }} prefix=":" digits={{ 1: { max: 5 } }} />
            </NumberFlowGroup>
          </span>
        )}
        <button type="button" className="ui-btn" aria-pressed={showNotes} onClick={() => setShowNotes((v) => !v)}>
          Notes
        </button>
        {(phase === "clarify" || phase === "intro") && (
          <button type="button" className="ui-btn ui-btn-primary" onClick={() => send({ type: "phase.advance", to: "coding" })}>
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

      <ResizablePanelGroup orientation="horizontal" className="rm-body">
        <ResizablePanel defaultSize="26%" minSize="18%">
          <section className="rm-panel rm-problem" aria-label="Problem">
            <header className="rm-panel-head">
              <span>{problem?.title ?? "Loading the problem…"}</span>
              {problem && (
                <span className="rm-tag">
                  {levelLabel(problem.difficulty)} · {problem.topics.map(levelLabel).join(", ")}
                </span>
              )}
            </header>
            {problem && (
              <Streamdown className="rm-md" mode="static" controls={false}>
                {problemMarkdown(problem)}
              </Streamdown>
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
                    <button type="button" className="ui-btn" onClick={() => run("run")} disabled={running || !editor || ended}>
                      {running ? "Running…" : "Run"}
                    </button>
                    <button
                      type="button"
                      className="ui-btn ui-btn-primary"
                      onClick={() => run("submit")}
                      disabled={running || !editor || ended}
                    >
                      Submit
                    </button>
                  </span>
                </header>
                <div className="rm-editor-host">
                  {code !== null ? (
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
            state={speaking ? "speaking" : state.interviewer}
            streamingId={state.streamingId}
            onStreamDone={streamDone}
            onAsk={(text) => send({ type: "chat.send", text })}
            onHint={() => send({ type: "hint.request" })}
            hintsLeft={ended ? 0 : 1}
            notes={showNotes ? notes : []}
            caption={caption}
            extra={
              state.session?.config.voice ? (
                <button type="button" className="ui-btn" aria-pressed={mic === "live"} onClick={toggleMic} disabled={ended}>
                  {MIC_LABEL[mic]}
                </button>
              ) : null
            }
          />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
