"use client";

import NumberFlow from "@number-flow/react";
import { AnimatePresence, m } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { LiquidGlass } from "@/components/theme/LiquidGlass";
import {
  clock,
  CLARIFY_QUESTION,
  codingReport,
  dimensionLabel,
  levelLabel,
  nudge,
  pasteFlag,
  problem,
  timeline,
  transcript,
  visibleRun,
} from "@/lib/fixtures";

// The tour replays the shared Quiet Streak fixture: its transcript, nudge, runs and report.
const report = codingReport;
const metrics = report.metrics;
const durationMs = metrics.duration_s * 1000;
const said = transcript[0];
const plannedAt = timeline.find((e) => e.kind === "transcript")?.t ?? said.end_ms;
// Statement markdown read aloud: drop the inline-code backticks.
const statement = problem.statement_md.replaceAll("`", "");
const hints = Object.values(metrics.hints_by_level).reduce((a, b) => a + b, 0);
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

// Stage fragments cross-fade with a short rise when the tab changes.
const stageMotion = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
  transition: { duration: 0.28, ease: [0.16, 1, 0.3, 1] as const },
};

// Rolls the overall score up from 0 each time the report stage opens.
function ScoreReveal({ value }: { value: number }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(value));
    return () => cancelAnimationFrame(id);
  }, [value]);
  return <NumberFlow value={shown} />;
}

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

export function HowItWorks({ codeHtml }: { codeHtml: string }) {
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
        <LiquidGlass
          data-ui
          id="hiw-panel"
          role="tabpanel"
          aria-labelledby={`hiw-tab-${active}`}
          className="hiw-frag"
          data-state={active}
        >
          <AnimatePresence mode="wait" initial={false}>
          {active === 0 && (
            <m.div key="chat" className="hf-chat" {...stageMotion}>
              <p className="msg msg-ai">
                <span className="msg-who">Interviewer</span>
                {statement}
              </p>
              <p className="msg msg-you">
                <span className="msg-who">You · text</span>
                {CLARIFY_QUESTION}
              </p>
              <p className="msg msg-ai">
                <span className="msg-who">Interviewer</span>
                No. Quiet means strictly below the threshold.
              </p>
              <p className="msg msg-you">
                <span className="msg-who">You · {said.source}</span>
                {said.text}
              </p>
              <div className="hf-plan">Stated plan recorded · {clock(plannedAt / 1000)}</div>
            </m.div>
          )}
          {active === 1 && (
            <m.div key="code" className="hf-code" {...stageMotion}>
              {/* Shiki HTML rendered on the server with the shared Ares code theme */}
              <div className="hf-shiki" translate="no" dangerouslySetInnerHTML={{ __html: codeHtml }} />
              <p className="msg msg-ai msg-nudge">
                <span className="msg-who">
                  Interviewer · {levelLabel(nudge.level)} · {clock(nudge.t / 1000)}
                </span>
                {nudge.text}
              </p>
              <div className="hf-runs">
                <span className="st st-done">
                  Run 1 · {visibleRun.passed} of {visibleRun.total} visible tests
                </span>
                <span>Noted · {pasteFlag.detail}</span>
              </div>
            </m.div>
          )}
          {active === 2 && (
            <m.div key="report" className="hf-report" {...stageMotion}>
              <div className="hf-overall">
                <strong>
                  <ScoreReveal value={report.overall} />
                </strong>
                <span>
                  Overall · {problem.title}, {problem.difficulty} · {clock(metrics.duration_s)}
                </span>
              </div>
              {report.dimensions.map((d) => (
                <div key={d.name} className="hf-dim">
                  <span>{dimensionLabel(d.name)}</span>
                  <span className="hf-track">
                    <span style={{ width: `${d.score * 10}%` }} />
                  </span>
                  <span className="hf-num">{d.score}</span>
                </div>
              ))}
              <div className="hf-scrub" aria-hidden>
                {report.moments.map((mo) => (
                  <span
                    key={mo.t}
                    className={mo.kind === "nudge" ? "mk mk-n" : "mk"}
                    style={{ left: `${(mo.t / durationMs) * 100}%` }}
                  />
                ))}
                <span className="hf-head" />
              </div>
              <div className="hf-legend">
                Replay · {plural(metrics.interventions_shown, "nudge")} · {plural(hints, "hint")} ·{" "}
                {plural(metrics.runs, "run")}
              </div>
            </m.div>
          )}
          </AnimatePresence>
        </LiquidGlass>
      </div>
    </div>
  );
}
