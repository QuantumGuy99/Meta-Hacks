"use client";

import { AnimatePresence, m } from "motion/react";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { RefreshCWIcon } from "@/components/ui/refresh-cw";
import { DRAFT_CODE, levelLabel, problem, submitResult } from "@/lib/fixtures";

// The hero's room plays a short, read-only scene on the Quiet Streak fixture: a candidate's draft is on
// screen, Ares (the AI agent) reads it line by line, finds the trailing-streak bug, types the one-line fix and re-runs
// the tests, narrating each step. It ends on why that matters: the model can fix it in seconds, so what an
// interview (or an incident) really tests is whether you can explain it. Everything derives from one clock,
// `t`, so pause and replay are just "stop the clock" and "set it to 0".

type Stage = "read" | "find" | "fix" | "test";

type Step = {
  at: number; // ms on the scene clock
  stage: Stage;
  lines: number[]; // 1-based lines to highlight in the code as it is at that moment
  label: string;
  text: string;
  tone?: "issue" | "ok";
};

const STAGES: [Stage, string][] = [
  ["read", "Read"],
  ["find", "Find"],
  ["fix", "Fix"],
  ["test", "Test"],
];

const DRAFT = DRAFT_CODE.trimEnd().split("\n");
const RETURN_LINE = DRAFT.findIndex((l) => l.trim() === "return best") + 1; // 1-based
const FIX_LINE = "    best = max(best, cur)";
const TOTAL_TESTS = submitResult.total;

const FIX_AT = 10_000;
const CHAR_MS = 40;
const STEPS: Step[] = [
  {
    at: 600,
    stage: "read",
    lines: [1, 2],
    label: "Reading the function",
    text: "`best` holds the longest quiet streak so far; `cur` counts the streak in progress.",
  },
  {
    at: 2_800,
    stage: "read",
    lines: [3, 4, 5],
    label: "Tracing the loop",
    text: "Every reading below the threshold makes the current streak one longer.",
  },
  {
    at: 5_000,
    stage: "read",
    lines: [6, 7, 8],
    label: "Tracing the loop",
    text: "A loud reading ends the streak: `best` keeps the longer one and `cur` starts over.",
  },
  {
    at: 7_400,
    stage: "find",
    lines: [RETURN_LINE],
    label: "Found the bug",
    text: "If the quiet stretch runs to the last reading, no loud reading comes after it, so it's never recorded. With every reading quiet, this returns 0.",
    tone: "issue",
  },
  {
    at: FIX_AT,
    stage: "fix",
    lines: [RETURN_LINE],
    label: "Writing the fix",
    text: "Once the loop ends, record the streak that's still running.",
  },
  {
    at: 11_800,
    stage: "test",
    lines: [RETURN_LINE],
    label: "Re-running the tests",
    text: `${TOTAL_TESTS} of ${TOTAL_TESTS} tests pass, including the one that failed.`,
    tone: "ok",
  },
];
const WHY_AT = 13_600;
const END = WHY_AT;
const TICK_MS = 100;

const KEYWORDS = /\b(def|for|in|if|else|return|max|int|list)\b/g;

/** Light syntax colour for the read-only code: keywords only, so the bug line stays readable. */
function colour(line: string): ReactNode {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of line.matchAll(KEYWORDS)) {
    parts.push(line.slice(last, match.index), <span key={match.index} className="cl-kw">{match[0]}</span>);
    last = match.index + match[0].length;
  }
  parts.push(line.slice(last));
  return parts;
}

/** Inline `code` in a narration line. */
function prose(text: string): ReactNode {
  return text.split(/(`[^`]+`)/).map((part, i) =>
    part.startsWith("`") ? <code key={i}>{part.slice(1, -1)}</code> : <Fragment key={i}>{part}</Fragment>,
  );
}

// Messages swap with a short rise (transform/opacity only).
const msgMotion = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
  transition: { duration: 0.32, ease: [0.16, 1, 0.3, 1] as const },
};

export function HeroRoom() {
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const clockRef = useRef(0); // the scene clock's source of truth; `t` mirrors it for rendering

  // Start once the room is on screen; under reduced motion, show the finished scene instead.
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const id = requestAnimationFrame(() => {
        clockRef.current = END;
        setT(END);
      });
      return () => cancelAnimationFrame(id);
    }
    const el = root.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setPlaying(true);
          io.disconnect();
        }
      },
      { threshold: 0.35 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // The scene clock: advances while playing and the tab is visible, stops at the end.
  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      if (document.hidden) return;
      clockRef.current = Math.min(END, clockRef.current + TICK_MS);
      setT(clockRef.current);
      if (clockRef.current >= END) setPlaying(false);
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, [playing]);

  const shown = STEPS.filter((s) => s.at <= t);
  const step = shown.at(-1);
  const stageIndex = step ? STAGES.findIndex(([s]) => s === step.stage) : -1;
  const done = t >= END;
  const why = t >= WHY_AT;

  // The fix line types in after FIX_AT; before that the draft is untouched.
  const typed = t < FIX_AT ? -1 : Math.min(FIX_LINE.length, Math.floor((t - FIX_AT) / CHAR_MS));
  const lines =
    typed < 0 ? DRAFT : [...DRAFT.slice(0, RETURN_LINE - 1), FIX_LINE.slice(0, typed), ...DRAFT.slice(RETURN_LINE - 1)];
  const typing = typed >= 0 && typed < FIX_LINE.length;
  // Once the fix is in, highlights after it shift down a line; the new line itself is the one to point at.
  const highlight = new Set(
    typed >= 0 ? [RETURN_LINE] : (step?.lines ?? []),
  );
  const bugLine = step?.stage === "find" ? RETURN_LINE : null;
  const addedLine = typed >= 0 ? RETURN_LINE : null;
  const seconds = (Math.min(t, WHY_AT) / 1000).toFixed(1);

  const replay = () => {
    clockRef.current = 0;
    setT(0);
    setPlaying(true);
  };

  return (
    <div data-ui className="room room-scene" aria-label="Demo: Ares fixing a candidate's code" ref={root}>
      <div className="room-bar">
        <ol className="room-phases" aria-label="What the model is doing">
          {STAGES.map(([s, name], i) => (
            <li key={s} aria-current={i === stageIndex && !why ? "step" : undefined} className={i < stageIndex || why ? "is-done" : undefined}>
              {name}
            </li>
          ))}
        </ol>
        <span className="room-badge">
          {problem.title} · {levelLabel(problem.difficulty)}
        </span>
        <span className="room-timer" aria-label={`Model time ${seconds} seconds`}>
          {seconds} s
        </span>
      </div>

      <div className="room-body">
        <div className="room-editor">
          <div className="room-file">
            solution.py <span className="room-file-note">· the candidate&apos;s draft, read-only</span>
          </div>
          <pre className="room-lines" aria-label="solution.py">
            {lines.map((line, i) => {
              const n = i + 1;
              const cls = [
                "cl",
                highlight.has(n) && !done ? "is-active" : "",
                n === bugLine ? "is-bug" : "",
                n === addedLine ? "is-added" : "",
              ]
                .filter(Boolean)
                .join(" ");
              return (
                <span key={i} className={cls}>
                  <span className="cl-n" aria-hidden>
                    {n}
                  </span>
                  <span className="cl-text">
                    {colour(line)}
                    {n === addedLine && typing && <span className="cl-caret" aria-hidden />}
                  </span>
                </span>
              );
            })}
          </pre>
        </div>

        <div className="room-side">
          <div className="room-who">
            <span className={playing && !done ? "dot dot-live" : "dot dot-idle"} />
            Ares · {done ? "done" : step ? step.label.toLowerCase() : "opening the file"}
          </div>

          <div className="room-msgs" aria-live="polite">
            <AnimatePresence mode="wait" initial={false}>
              {why ? (
                <m.div key="why" className="room-why" {...msgMotion}>
                  <span className="msg-who">Why this matters</span>
                  <p>
                    Ares found and fixed that in seconds. Writing the fix isn&apos;t the hard part
                    anymore.
                  </p>
                  <p>
                    In an interview or an incident, <strong>you&apos;re the one asked why it broke</strong>.
                    Ares makes you show you understand your code, not just that it passes.
                  </p>
                </m.div>
              ) : step ? (
                <m.p
                  key={step.at}
                  className={`msg msg-ai ${step.tone === "issue" ? "msg-nudge" : step.tone === "ok" ? "msg-ok" : ""}`}
                  {...msgMotion}
                >
                  <span className="msg-who">{step.label}</span>
                  {prose(step.text)}
                </m.p>
              ) : null}
            </AnimatePresence>
          </div>

          <div className="room-actions">
            {done ? (
              <button type="button" className="ui-btn" onClick={replay}>
                <RefreshCWIcon size={14} aria-hidden />
                Replay
              </button>
            ) : (
              <button type="button" className="ui-btn" onClick={() => setPlaying((p) => !p)}>
                {playing ? "Pause" : "Play"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
