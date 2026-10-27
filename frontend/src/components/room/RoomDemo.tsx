"use client";

import NumberFlow, { NumberFlowGroup } from "@number-flow/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Streamdown } from "streamdown";
import { toast } from "sonner";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { CodeEditor, type FlaggedLine } from "./CodeEditor";
import { InterviewerPanel, type InterviewerState, type RoomMessage } from "./InterviewerPanel";
import { TestPanel, type RunResult } from "./TestPanel";

// Scripted demo of the interview room. Everything the backend will drive over the session
// WebSocket (interviewer messages, run results, notes) is faked locally here.

const PROBLEM = `Given hourly temperature readings \`temps\` and a tolerance \`k\`, return the length of the
**longest run of consecutive readings** where the highest and lowest reading differ by at most \`k\`.

**Example**
- \`temps = [4, 6, 5, 9, 8]\`, \`k = 2\` → \`3\` (the run \`4, 6, 5\`)

**Constraints**
- \`0 ≤ len(temps) ≤ 10⁵\`
- Readings can be negative; \`k ≥ 0\``;

const STARTER = `def longest_steady_run(temps: list[int], k: int) -> int:
    best = 1
    left = 0
    for right in range(len(temps)):
        window = temps[left:right + 1]
        while max(window) - min(window) > k:
            left += 1
            window = temps[left:right + 1]
        best = max(best, right - left + 1)
    return best
`;

const HINTS = [
  "Look at what `best` starts as.",
  "What should the function return when `temps` is empty?",
  "Guard the empty case before the loop, or start `best` at 0.",
];

const PHASES = ["Clarify", "Coding", "Wrap up"] as const;
const LIMIT_S = 30 * 60;

let seq = 0;
const nextId = () => `m${++seq}`;

function handlesEmpty(code: string) {
  return /if\s+not\s+temps\s*:/.test(code) || /len\(\s*temps\s*\)\s*==\s*0/.test(code) || /best\s*=\s*0\b/.test(code);
}

function fakeRun(code: string, kind: "run" | "submit"): RunResult {
  const empty = handlesEmpty(code);
  return {
    kind,
    runtimeMs: 38 + Math.round(Math.random() * 20),
    cases: [
      { id: "t1", passed: true, input: "[4, 6, 5, 9, 8], k=2", expected: "3", actual: "3" },
      { id: "t2", passed: true, input: "[1, 1, 1], k=0", expected: "3", actual: "3" },
      { id: "t3", passed: empty, input: "[], k=3", expected: "0", actual: empty ? "0" : "1" },
      { id: "t4", passed: true, input: "[-2, 5, -1, 0], k=3", expected: "3", actual: "3" },
    ],
  };
}

export function RoomDemo() {
  const [code, setCode] = useState(STARTER);
  const [phase, setPhase] = useState(0);
  const [remaining, setRemaining] = useState(LIMIT_S);
  const [messages, setMessages] = useState<RoomMessage[]>([]);
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const [state, setState] = useState<InterviewerState>("thinking");
  const [hintsUsed, setHintsUsed] = useState(0);
  const [result, setResult] = useState<RunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [flagged, setFlagged] = useState<FlaggedLine[]>([]);
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
    (text: string, level?: RoomMessage["level"]) => {
      queue.current.push({ id: nextId(), who: "interviewer", level, text });
      if (!streaming.current) startNext();
    },
    [startNext],
  );

  const onStreamDone = startNext;

  // Intro.
  useEffect(() => {
    const id = window.setTimeout(
      () => say("Hi, I’m your interviewer today. Read the problem on the left, ask anything that’s unclear, then talk me through your approach before you code.", "Info"),
      500,
    );
    return () => window.clearTimeout(id);
  }, [say]);

  // Countdown.
  useEffect(() => {
    const id = window.setInterval(() => setRemaining((s) => Math.max(0, s - 1)), 1000);
    return () => window.clearInterval(id);
  }, []);

  // The flag disappears as soon as the empty case is handled.
  const emptyHandled = useMemo(() => handlesEmpty(code), [code]);
  const shownFlags = emptyHandled ? [] : flagged;

  const ask = (text: string) => {
    setMessages((list) => [...list, { id: nextId(), who: "you", text }]);
    if (phase === 0) setPhase(1);
    setState("thinking");
    const reply = /negative/i.test(text)
      ? "Yes, readings can be negative. A run where max minus min equals `k` still counts."
      : /window|deque|two pointer/i.test(text)
        ? "That approach works. What will you return for an empty list?"
        : "Good. State your approach in a sentence, then start coding. I’ll stay quiet unless something needs a look.";
    window.setTimeout(() => say(reply), 700);
  };

  const hint = () => {
    if (hintsUsed >= HINTS.length) return;
    const levels = ["Nudge", "Question", "Hint"] as const;
    say(HINTS[hintsUsed], levels[hintsUsed]);
    setHintsUsed((n) => n + 1);
  };

  const run = (kind: "run" | "submit") => {
    if (running) return;
    if (phase === 0) setPhase(1);
    setRunning(true);
    setResult(null);
    window.setTimeout(() => {
      const r = fakeRun(code, kind);
      setResult(r);
      setRunning(false);
      const failed = r.cases.filter((c) => !c.passed).length;
      if (failed) {
        toast.error(`${failed} of ${r.cases.length} tests failed`, { description: "The interviewer flagged a line." });
        setFlagged([{ line: 2, note: "What does this return for an empty list?" }]);
        say("You mentioned handling an empty list. I don’t see that yet.", "Nudge");
      } else if (kind === "submit") {
        setPhase(2);
        toast.success("Submitted: 22 of 22 hidden tests passed", {
          action: { label: "See Report", onClick: () => router.push("/report/demo") },
        });
        say("All hidden tests pass. Last question: what’s the time complexity of your window, and could you avoid re-slicing?", "Question");
      } else {
        toast.success("All visible tests passed");
        say("Visible tests pass. Submit when you’re ready.", "Info");
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
        <span className="room-badge">Active feedback · Demo</span>
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
              <span>Longest Steady Run</span>
              <span className="rm-tag">Medium · Sliding window</span>
            </header>
            <Streamdown className="rm-md" mode="static" controls={false}>
              {PROBLEM}
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
                  <span className="rm-actions">
                    <button type="button" className="ui-btn" onClick={() => run("run")} disabled={running}>
                      Run
                    </button>
                    <button type="button" className="ui-btn ui-btn-primary" onClick={() => run("submit")} disabled={running}>
                      Submit
                    </button>
                  </span>
                </header>
                <div className="rm-editor-host">
                  <CodeEditor
                    value={code}
                    onChange={(v) => {
                      setCode(v);
                      if (phase === 0) setPhase(1);
                    }}
                    flagged={shownFlags}
                    onRun={() => run("run")}
                  />
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
            onStreamDone={onStreamDone}
            onAsk={ask}
            onHint={hint}
            hintsLeft={HINTS.length - hintsUsed}
          />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
