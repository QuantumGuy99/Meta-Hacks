"use client";

import NumberFlow, { NumberFlowGroup } from "@number-flow/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Streamdown } from "streamdown";
import { toast } from "sonner";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { attachEditorCapture, type EditorCapture } from "@/lib/capture/editor";
import {
  analysis,
  clock,
  codingReport,
  codingSession,
  DRAFT_CODE,
  levelLabel,
  nudge,
  pasteFlag,
  problem,
  recordsTrailingStreak,
  S2_HINTS,
  sessionState,
  STEP_TITLES,
  submitResult,
  visibleRun,
  WRAP_UP_QUESTION,
} from "@/lib/fixtures";
import type { ClientMessage, InterventionLevel, RunResult, StepStatus } from "@/types/contracts";
import { CodeEditor, type FlaggedLine } from "./CodeEditor";
import { InterviewerPanel, type InterviewerState, type RoomMessage, type RoomNote } from "./InterviewerPanel";
import { TestPanel } from "./TestPanel";

// Scripted demo of the interview room on the shared Quiet Streak fixture. Everything the
// backend will drive over the session WebSocket (messages, run results, notes) is replayed
// from those fixtures locally. Edits go through the real capture lib (lib/capture/editor.ts); with no
// backend yet, its messages are counted here and pastes become the same neutral note the server would send.

const PROBLEM_MD = [
  problem.statement_md,
  "**Example**",
  ...problem.examples.map((e) => `- \`${e.input}\` → \`${e.output}\`${e.explanation ? `: ${e.explanation}` : ""}`),
  "**Constraints**",
  ...problem.constraints.map((c) => `- \`${c}\``),
].join("\n\n");

const PHASES = ["Clarify", "Coding", "Wrap up"] as const;
const issue = analysis.issues[0];

let seq = 0;
const nextId = () => `m${++seq}`;

// The same submission once the trailing streak is recorded: every case passes.
const passingSubmit: RunResult = {
  ...submitResult,
  run_id: "r3",
  passed: submitResult.total,
  cases: submitResult.cases.map((c) => ({ ...c, passed: true, error: null, actual_repr: c.expected_repr })),
};

function reply(text: string) {
  if (/equal|threshold/i.test(text)) return "No. Quiet means strictly below the threshold.";
  if (/empty|no readings/i.test(text)) return "Good: an empty list returns 0.";
  if (/count|single pass|one pass|loop/i.test(text))
    return "That plan works. Keep an eye on when you record the best length.";
  return "Good. State your approach in a sentence, then start coding. I’ll stay quiet unless something needs a look.";
}

export function RoomDemo() {
  const [code, setCode] = useState(DRAFT_CODE);
  const [phase, setPhase] = useState(1);
  const [remaining, setRemaining] = useState(sessionState.remaining_s ?? codingSession.time_limit_s);
  // Pick up mid-session: the candidate's stated plan is already on record.
  const [messages, setMessages] = useState<RoomMessage[]>(() => [
    { id: "plan", who: "you", text: analysis.stated_plan ?? "" },
  ]);
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const [state, setState] = useState<InterviewerState>(sessionState.interviewer_state);
  const [hintsUsed, setHintsUsed] = useState(0);
  const [result, setResult] = useState<RunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [flagged, setFlagged] = useState<FlaggedLine[]>([]);
  const [sent, setSent] = useState(0);
  const [pasteNotes, setPasteNotes] = useState<string[]>([]);
  const capture = useRef<EditorCapture | null>(null);
  const editorRef = useRef<Parameters<NonNullable<Parameters<typeof CodeEditor>[0]["onEditor"]>>[0] | null>(null);
  const queue = useRef<RoomMessage[]>([]);
  const streaming = useRef<string | null>(null);
  const router = useRouter();

  // Interviewer speech is queued so only one message streams at a time.
  const startNext = useCallback(() => {
    const msg = queue.current.shift();
    streaming.current = msg?.id ?? null;
    setStreamingId(streaming.current);
    if (!msg) {
      setState("listening");
      return;
    }
    setMessages((list) => [...list, msg]);
    setState("speaking");
  }, []);

  const say = useCallback(
    (text: string, level?: InterventionLevel) => {
      queue.current.push({ id: nextId(), who: "interviewer", level, text });
      if (!streaming.current) startNext();
    },
    [startNext],
  );

  useEffect(() => {
    const id = window.setTimeout(
      () => say("Sounds good. Go ahead and code it; I’ll stay quiet unless something needs a look.", "info"),
      600,
    );
    return () => window.clearTimeout(id);
  }, [say]);

  // Stand-in for the session socket: count what the capture lib sends, and turn pastes into notes.
  const send = useCallback((msg: ClientMessage) => {
    setSent((n) => n + (msg.type === "editor.events" ? msg.events.length : 1));
    if (msg.type !== "editor.events") return;
    for (const e of msg.events) {
      if (e.kind === "paste" && e.pasted_chars) {
        setPasteNotes((list) => [...list, `Pasted ${e.pasted_chars} chars at ${clock(e.t / 1000)}`]);
      }
    }
  }, []);

  const onEditor = useCallback(
    (editor: NonNullable<typeof editorRef.current>) => {
      editorRef.current = editor;
      capture.current?.dispose();
      // The session is already this far in: event times continue from the fixture's clock.
      const elapsedMs = (codingSession.time_limit_s - (sessionState.remaining_s ?? 0)) * 1000;
      capture.current = attachEditorCapture(editor, send, { startedAtMs: Date.now() - elapsedMs });
    },
    [send],
  );
  useEffect(() => () => capture.current?.dispose(), []);

  // Countdown.
  useEffect(() => {
    const id = window.setInterval(() => setRemaining((s) => Math.max(0, s - 1)), 1000);
    return () => window.clearInterval(id);
  }, []);

  // The flag clears as soon as the trailing streak is recorded.
  const fixed = useMemo(() => recordsTrailingStreak(code), [code]);
  const shownFlags = fixed ? [] : flagged;

  const steps = analysis.steps.map((s) => {
    const done = s.step_id === "s2" && fixed;
    const after = codingReport.coding?.steps.find((r) => r.step_id === s.step_id);
    return {
      title: STEP_TITLES[s.step_id] ?? s.step_id,
      status: (done ? "done" : s.status) as StepStatus,
      evidence: done ? (after?.evidence ?? s.evidence) : s.evidence,
    };
  });
  const notes: RoomNote[] = [
    ...steps,
    { title: pasteFlag.detail.charAt(0).toUpperCase() + pasteFlag.detail.slice(1), status: "noted" },
    ...pasteNotes.map((title) => ({ title, status: "noted" as const })),
  ];

  // Resetting is a programmatic edit: the capture lib snapshots it instead of logging it as typing.
  const reset = () => {
    const editor = editorRef.current;
    if (!editor) return;
    if (capture.current) capture.current.programmatic(() => editor.setValue(problem.starter_code));
    else editor.setValue(problem.starter_code);
    setFlagged([]);
    setResult(null);
  };

  const ask = (text: string) => {
    setMessages((list) => [...list, { id: nextId(), who: "you", text }]);
    setState("thinking");
    window.setTimeout(() => say(reply(text)), 700);
  };

  const hint = () => {
    if (hintsUsed >= S2_HINTS.length) return;
    const h = S2_HINTS[hintsUsed];
    say(h.text, h.level);
    setHintsUsed((n) => n + 1);
  };

  const run = (kind: "run" | "submit") => {
    if (running) return;
    // The backend must see the exact code being run.
    capture.current?.snapshot();
    setRunning(true);
    setResult(null);
    window.setTimeout(() => {
      const r = kind === "run" ? visibleRun : fixed ? passingSubmit : submitResult;
      setResult(r);
      setRunning(false);
      const failed = r.total - r.passed;
      if (failed) {
        toast.error(`${failed} of ${r.total} tests failed`, { description: "The interviewer flagged a line." });
        if (issue?.line) setFlagged([{ line: issue.line, note: issue.description }]);
        say(nudge.text, nudge.level);
      } else if (kind === "submit") {
        setPhase(2);
        toast.success(`Submitted: ${r.passed} of ${r.total} tests passed`, {
          action: { label: "See Report", onClick: () => router.push("/report/demo") },
        });
        say(`All tests pass. Last question: ${WRAP_UP_QUESTION}`, "question");
      } else {
        toast.success("All visible tests passed");
        say("Visible tests pass. Submit when you’re ready.", "info");
      }
    }, 800);
  };

  const mins = Math.floor(remaining / 60);
  const secs = remaining % 60;

  return (
    <div className="rm" data-ui>
      <header className="rm-top">
        <Link href="/" className="rm-brand" translate="no">
          Crucible
        </Link>
        <ol className="room-phases" aria-label="Interview phase">
          {PHASES.map((p, i) => (
            <li key={p} aria-current={i === phase ? "step" : undefined}>
              {p}
            </li>
          ))}
        </ol>
        <span className="room-badge">{levelLabel(codingSession.config.feedback ?? "active")} feedback · Demo</span>
        <span className="rm-timer" aria-label={`${mins} minutes ${secs} seconds left`}>
          <NumberFlowGroup>
            <NumberFlow value={mins} format={{ minimumIntegerDigits: 2 }} />
            <NumberFlow value={secs} format={{ minimumIntegerDigits: 2 }} prefix=":" digits={{ 1: { max: 5 } }} />
          </NumberFlowGroup>
        </span>
        <Link href="/report/demo" className="ui-btn">
          End
        </Link>
      </header>

      <ResizablePanelGroup orientation="horizontal" className="rm-body">
        <ResizablePanel defaultSize="26%" minSize="18%">
          <section className="rm-panel rm-problem" aria-label="Problem">
            <header className="rm-panel-head">
              <span>{problem.title}</span>
              <span className="rm-tag">
                {levelLabel(problem.difficulty)} · {problem.topics.map(levelLabel).join(", ")}
              </span>
            </header>
            <Streamdown className="rm-md" mode="static" controls={false}>
              {PROBLEM_MD}
            </Streamdown>
          </section>
        </ResizablePanel>
        <ResizableHandle />
        <ResizablePanel defaultSize="48%" minSize="30%">
          <ResizablePanelGroup orientation="vertical">
            <ResizablePanel defaultSize="68%" minSize="30%">
              <section className="rm-panel rm-editor" aria-label="Editor">
                <header className="rm-panel-head">
                  <span translate="no">solution.py</span>
                  <span className="rm-capture" aria-live="off" title="Edit events sent by the capture library">
                    Capture · <NumberFlow value={sent} /> events
                  </span>
                  <span className="rm-actions">
                    <button type="button" className="ui-btn" onClick={reset}>
                      Reset Code
                    </button>
                    <button type="button" className="ui-btn" onClick={() => run("run")} disabled={running}>
                      Run
                    </button>
                    <button type="button" className="ui-btn ui-btn-primary" onClick={() => run("submit")} disabled={running}>
                      Submit
                    </button>
                  </span>
                </header>
                <div className="rm-editor-host">
                  <CodeEditor value={code} onChange={setCode} flagged={shownFlags} onRun={() => run("run")} onEditor={onEditor} />
                </div>
              </section>
            </ResizablePanel>
            <ResizableHandle />
            <ResizablePanel defaultSize="32%" minSize="15%">
              <TestPanel result={result} running={running} />
            </ResizablePanel>
          </ResizablePanelGroup>
        </ResizablePanel>
        <ResizableHandle />
        <ResizablePanel defaultSize="26%" minSize="20%">
          <InterviewerPanel
            messages={messages}
            state={state}
            streamingId={streamingId}
            onStreamDone={startNext}
            onAsk={ask}
            onHint={hint}
            hintsLeft={S2_HINTS.length - hintsUsed}
            notes={notes}
          />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
