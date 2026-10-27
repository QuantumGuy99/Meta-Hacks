"use client";

import NumberFlow from "@number-flow/react";
import { AnimatePresence, m } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { RefreshCWIcon } from "@/components/ui/refresh-cw";

// A working crop of the interview room: edit the code and the interviewer's notes react.
// Sample problem written for this page; real problems come from data/problems.
const STARTER = `def longest_steady_run(temps: list[int], k: int) -> int:
    best = 1
    left = 0
    for right in range(len(temps)):
        window = temps[left:right + 1]
        while max(window) - min(window) > k:
            left += 1
            window = temps[left:right + 1]
        best = max(best, right - left + 1)
    return best`;

const HINTS = [
  { level: "Nudge", text: "Look at what best starts as." },
  { level: "Question", text: "What should the function return when temps is empty?" },
  { level: "Hint", text: "Guard the empty case before the loop, or start best at 0." },
];

// Messages slide in from below and reflow the list (transform/opacity only).
const msgMotion = {
  layout: "position" as const,
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
  transition: { duration: 0.32, ease: [0.16, 1, 0.3, 1] as const },
};

export function HeroRoom() {
  const [code, setCode] = useState(STARTER);
  const [hintsUsed, setHintsUsed] = useState(0);

  const emptyHandled = useMemo(
    () =>
      /if\s+not\s+temps\s*:/.test(code) ||
      /len\(\s*temps\s*\)\s*==\s*0/.test(code) ||
      /best\s*=\s*0\b/.test(code),
    [code],
  );
  const lines = code.split("\n").length;

  // Toast once when the missing step turns done.
  const wasHandled = useRef(emptyHandled);
  useEffect(() => {
    if (emptyHandled && !wasHandled.current) {
      toast.success("Step done: Handle empty input", { description: "The interviewer updated its notes." });
    }
    wasHandled.current = emptyHandled;
  }, [emptyHandled]);

  return (
    <div data-ui className="room" aria-label="Interview room demo">
      <div className="room-bar">
        <ol className="room-phases" aria-label="Interview phase">
          <li>Clarify</li>
          <li aria-current="step">Coding</li>
          <li>Wrap up</li>
        </ol>
        <span className="room-badge">Active feedback</span>
        <span className="room-timer" aria-label="Time remaining">
          18:42
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
            <span className={emptyHandled ? "dot dot-idle" : "dot dot-live"} />
            Interviewer · {emptyHandled ? "listening" : "speaking"}
          </div>

          <p className="msg msg-you">
            <span className="msg-who">You</span>
            Sliding window over the readings. Empty list returns 0.
          </p>

          <div className="room-msgs" aria-live="polite">
            <AnimatePresence mode="popLayout" initial={false}>
              {emptyHandled ? (
                <m.p key="ok" className="msg msg-ai msg-ok" {...msgMotion}>
                  <span className="msg-who">Interviewer · Info</span>
                  Good, the empty case is covered now. What does the slice on line 5 cost you?
                </m.p>
              ) : (
                <m.p key="nudge" className="msg msg-ai msg-nudge" {...msgMotion}>
                  <span className="msg-who">Interviewer · Nudge</span>
                  You mentioned handling an empty list. I don’t see that yet.
                </m.p>
              )}
              {HINTS.slice(0, hintsUsed).map((h) => (
                <m.p key={h.level} className="msg msg-ai" {...msgMotion}>
                  <span className="msg-who">Interviewer · {h.level}</span>
                  {h.text}
                </m.p>
              ))}
            </AnimatePresence>
          </div>

          <div className="room-notes" aria-label="Interviewer's notes">
            <div className="note">
              <span className={emptyHandled ? "st st-done" : "st st-miss"}>
                {emptyHandled ? "Done" : "Missing"}
              </span>
              Handle empty input
            </div>
            <div className="note">
              <span className="st st-done">Done</span>
              Grow and shrink the window
            </div>
            <div className="note">
              <span className="st st-prog">Watching</span>
              Window min and max in O(1)
            </div>
          </div>

          <div className="room-actions">
            <button
              type="button"
              className="ui-btn"
              onClick={() => setHintsUsed((n) => Math.min(n + 1, HINTS.length))}
              disabled={hintsUsed >= HINTS.length}
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
                setCode(STARTER);
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
