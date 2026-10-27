"use client";

import NumberFlow from "@number-flow/react";
import { AnimatePresence, m } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { RefreshCWIcon } from "@/components/ui/refresh-cw";
import {
  analysis,
  clock,
  DRAFT_CODE,
  levelLabel,
  nudge,
  pasteFlag,
  problem,
  recordsTrailingStreak,
  S2_HINTS,
  sessionState,
  STEP_TITLES,
  WRAP_UP_QUESTION,
} from "@/lib/fixtures";

// A working crop of the interview room on the shared Quiet Streak fixture: fix the trailing
// streak in the draft and the interviewer's notes react.

// The nudge is already on screen, so Hint climbs the rest of the s2 ladder.
const HINTS = S2_HINTS.slice(1);

// Messages slide in from below and reflow the list (transform/opacity only).
const msgMotion = {
  layout: "position" as const,
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
  transition: { duration: 0.32, ease: [0.16, 1, 0.3, 1] as const },
};

export function HeroRoom() {
  const [code, setCode] = useState(DRAFT_CODE);
  const [hintsUsed, setHintsUsed] = useState(0);

  const fixed = useMemo(() => recordsTrailingStreak(code), [code]);
  const lines = code.split("\n").length;

  // Toast once when the missing step turns done.
  const wasFixed = useRef(fixed);
  useEffect(() => {
    if (fixed && !wasFixed.current) {
      toast.success(`Step done: ${STEP_TITLES.s2}`, { description: "The interviewer updated its notes." });
    }
    wasFixed.current = fixed;
  }, [fixed]);

  return (
    <div data-ui className="room" aria-label="Interview room demo">
      <div className="room-bar">
        <ol className="room-phases" aria-label="Interview phase">
          <li>Clarify</li>
          <li aria-current="step">Coding</li>
          <li>Wrap up</li>
        </ol>
        <span className="room-badge">
          {problem.title} · {levelLabel(problem.difficulty)}
        </span>
        <span className="room-timer" aria-label="Time remaining">
          {clock(sessionState.remaining_s ?? 0)}
        </span>
      </div>

      <div className="room-body">
        <div className="room-editor">
          <div className="room-file">solution.py</div>
          <div className="room-code">
            <div className="room-gutter" aria-hidden>
              {Array.from({ length: lines }, (_, i) => (
                <span key={i}>{i + 1}</span>
              ))}
            </div>
            <textarea
              aria-label="Solution code, editable"
              spellCheck={false}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              // one spare row so a horizontal scrollbar never hides the last line
              rows={Math.max(lines + 1, 11)}
            />
          </div>
        </div>

        <div className="room-side">
          <div className="room-who">
            <span className={fixed ? "dot dot-idle" : "dot dot-live"} />
            Interviewer · {fixed ? "listening" : "speaking"}
          </div>

          <p className="msg msg-you">
            <span className="msg-who">You · voice</span>
            {analysis.stated_plan}
          </p>

          <div className="room-msgs" aria-live="polite">
            <AnimatePresence mode="popLayout" initial={false}>
              {fixed ? (
                <m.p key="ok" className="msg msg-ai msg-ok" {...msgMotion}>
                  <span className="msg-who">Interviewer · Question</span>
                  That covers a streak that runs to the end. {WRAP_UP_QUESTION}
                </m.p>
              ) : (
                <m.p key="nudge" className="msg msg-ai msg-nudge" {...msgMotion}>
                  <span className="msg-who">Interviewer · {levelLabel(nudge.level)}</span>
                  {nudge.text}
                </m.p>
              )}
              {HINTS.slice(0, hintsUsed).map((h) => (
                <m.p key={h.level} className="msg msg-ai" {...msgMotion}>
                  <span className="msg-who">Interviewer · {levelLabel(h.level)}</span>
                  {h.text}
                </m.p>
              ))}
            </AnimatePresence>
          </div>

          <div className="room-notes" aria-label="Interviewer's notes">
            <div className="note">
              <span className="st st-done">Done</span>
              {STEP_TITLES.s1}
            </div>
            <div className="note">
              <span className={fixed ? "st st-done" : "st st-miss"}>{fixed ? "Done" : "Missing"}</span>
              {STEP_TITLES.s2}
            </div>
            <div className="note">
              <span className="st st-prog">Noted</span>
              {pasteFlag.detail.charAt(0).toUpperCase() + pasteFlag.detail.slice(1)}
            </div>
          </div>

          <div className="room-actions">
            <button
              type="button"
              className="ui-btn"
              onClick={() => setHintsUsed((n) => Math.min(n + 1, HINTS.length))}
              disabled={fixed || hintsUsed >= HINTS.length}
            >
              Hint
              {hintsUsed > 0 && (
                <span className="btn-count">
                  <NumberFlow value={hintsUsed} /> used
                </span>
              )}
            </button>
            <button
              type="button"
              className="ui-btn"
              onClick={() => {
                setCode(DRAFT_CODE);
                setHintsUsed(0);
              }}
            >
              <RefreshCWIcon size={14} aria-hidden />
              Reset
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
