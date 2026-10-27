"use client";

import { useEffect, useRef, useState } from "react";

const STEPS = [
  {
    title: "Talk through your approach first.",
    line: "Ask clarifying questions and state a plan, out loud or in chat. The interviewer answers from the problem spec only.",
  },
  {
    title: "Then code while it watches.",
    line: "Every edit streams to the interviewer. In active mode it steps in at sensible moments, and never with code.",
  },
  {
    title: "Finish with a replay, not a verdict.",
    line: "Five scores, three strengths, three things to improve, and your session played back with every nudge on the timeline.",
  },
];

export function HowItWorks() {
  const [active, setActive] = useState(0);
  // Steps advance on their own until the visitor picks one.
  const [auto, setAuto] = useState(true);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!auto || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let visible = false;
    const io = new IntersectionObserver(([e]) => (visible = e.isIntersecting), { threshold: 0.4 });
    if (root.current) io.observe(root.current);
    const id = setInterval(() => visible && setActive((a) => (a + 1) % STEPS.length), 5000);
    return () => {
      clearInterval(id);
      io.disconnect();
    };
  }, [auto]);

  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const pick = (i: number, focus = false) => {
    setActive(i);
    setAuto(false);
    if (focus) tabs.current[i]?.focus();
  };

  return (
    <div className="hiw" ref={root}>
      <div className="hiw-text">
        <div
          className="hiw-tabs"
          role="tablist"
          aria-label="Interview Stages"
          onKeyDown={(e) => {
            const n = STEPS.length;
            if (e.key === "ArrowDown" || e.key === "ArrowRight") pick((active + 1) % n, true);
            else if (e.key === "ArrowUp" || e.key === "ArrowLeft") pick((active + n - 1) % n, true);
            else if (e.key === "Home") pick(0, true);
            else if (e.key === "End") pick(n - 1, true);
            else return;
            e.preventDefault();
          }}
        >
          {STEPS.map((s, i) => (
            <button
              key={s.title}
              ref={(el) => {
                tabs.current[i] = el;
              }}
              id={`hiw-tab-${i}`}
              type="button"
              role="tab"
              aria-selected={i === active}
              aria-controls="hiw-panel"
              tabIndex={i === active ? 0 : -1}
              className={i === active ? "hiw-step is-active" : "hiw-step"}
              onClick={() => pick(i)}
            >
              <span className="hiw-title">{s.title}</span>
              <span className="hiw-line">{s.line}</span>
            </button>
          ))}
        </div>
        <button type="button" className="lp-link hiw-pause" onClick={() => setAuto((a) => !a)}>
          {auto ? "Pause the Tour" : "Play the Tour"}
        </button>
      </div>

      <div className="hiw-stage">
        <div
          data-ui
          id="hiw-panel"
          role="tabpanel"
          aria-labelledby={`hiw-tab-${active}`}
          className="hiw-frag"
          data-state={active}
        >
          {active === 0 && (
            <div className="hf-chat">
              <p className="msg msg-ai">
                <span className="msg-who">Interviewer</span>
                Given hourly temperature readings and a tolerance k, find the longest run where the
                readings stay within k of each other.
              </p>
              <p className="msg msg-you">
                <span className="msg-who">You · voice</span>
                Can readings be negative? And is k inclusive?
              </p>
              <p className="msg msg-ai">
                <span className="msg-who">Interviewer</span>
                Yes to both. A run where max minus min equals k counts.
              </p>
              <p className="msg msg-you">
                <span className="msg-who">You · voice</span>
                Then a sliding window, tracking min and max with two deques. Linear time.
              </p>
              <div className="hf-plan">Stated plan recorded · 1:12</div>
            </div>
          )}
          {active === 1 && (
            <div className="hf-code">
              <pre>
                <code>{`for right, t in enumerate(temps):
    while lows and temps[lows[-1]] >= t:
        lows.pop()
    lows.append(right)
    while highs and temps[highs[-1]] <= t:
        highs.pop()
    highs.append(right)
    while temps[highs[0]] - temps[lows[0]] > k:
        left += 1`}</code>
              </pre>
              <p className="msg msg-ai msg-nudge">
                <span className="msg-who">Interviewer · Nudge</span>
                Your loop moves left, but the deques may still hold indexes before it. Worth a second
                look.
              </p>
              <div className="hf-runs">
                <span className="st st-miss">Run 2 · 3 of 4 visible tests</span>
                <span>Paste noted · 0 chars</span>
              </div>
            </div>
          )}
          {active === 2 && (
            <div className="hf-report">
              <div className="hf-overall">
                <strong>78</strong>
                <span>Overall, medium problem, 31 min</span>
              </div>
              {[
                ["Problem solving", 8],
                ["Correctness", 7],
                ["Code quality", 8],
                ["Communication", 9],
                ["Independence", 6],
              ].map(([name, score]) => (
                <div key={name} className="hf-dim">
                  <span>{name}</span>
                  <span className="hf-track">
                    <span style={{ width: `${(score as number) * 10}%` }} />
                  </span>
                  <span className="hf-num">{score}</span>
                </div>
              ))}
              <div className="hf-scrub" aria-hidden>
                <span className="mk mk-n" style={{ left: "22%" }} />
                <span className="mk" style={{ left: "41%" }} />
                <span className="mk mk-n" style={{ left: "58%" }} />
                <span className="mk" style={{ left: "83%" }} />
                <span className="hf-head" />
              </div>
              <div className="hf-legend">Replay · 2 nudges · 1 hint · 4 runs</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
