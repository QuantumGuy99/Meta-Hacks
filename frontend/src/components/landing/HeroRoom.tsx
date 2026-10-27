"use client";

import { useMemo, useState } from "react";

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

          {emptyHandled ? (
            <p className="msg msg-ai msg-ok" aria-live="polite">
              <span className="msg-who">Interviewer · Info</span>
              Good, the empty case is covered now. What does the slice on line 5 cost you?
            </p>
          ) : (
            <p className="msg msg-ai msg-nudge" aria-live="polite">
              <span className="msg-who">Interviewer · Nudge</span>
              You mentioned handling an empty list. I don’t see that yet.
            </p>
          )}

          {HINTS.slice(0, hintsUsed).map((h) => (
            <p key={h.level} className="msg msg-ai">
              <span className="msg-who">Interviewer · {h.level}</span>
              {h.text}
            </p>
          ))}

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
              Hint {hintsUsed > 0 ? `(${hintsUsed} used)` : ""}
            </button>
            <button type="button" className="ui-btn" onClick={() => { setCode(STARTER); setHintsUsed(0); }}>
              Reset
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
