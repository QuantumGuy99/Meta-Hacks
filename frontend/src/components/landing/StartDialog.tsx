"use client";

import { AnimatePresence, m } from "motion/react";
import { useRouter } from "next/navigation";
import { useState, type CSSProperties } from "react";
import { levelLabel, problem, project } from "@/lib/fixtures";
import type { FeedbackLevel, Mode } from "@/types/contracts";

const MODES: [Mode, string][] = [
  ["coding", "Coding Interview"],
  ["defense", "Project Defense"],
];

// Sample projects a defense can start from until upload lands (the fixture's bank-transfer).
const SAMPLES = [project];

// The field under the mode switch swaps with a short cross-fade.
const fieldMotion = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4 },
  transition: { duration: 0.2, ease: [0.23, 1, 0.32, 1] as const },
};

// One dialog for both modes, so neither reads as the secondary option.
export function StartDialog() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("coding");
  const [topic, setTopic] = useState(levelLabel(problem.topics[0] ?? ""));
  const [projectId, setProjectId] = useState(SAMPLES[0].id);
  const [feedback, setFeedback] = useState<FeedbackLevel>("active");
  const label = MODES.find(([v]) => v === mode)![1];

  return (
    <form
      data-ui
      className="dlg"
      aria-labelledby="dlg-title"
      onSubmit={(e) => {
        e.preventDefault();
        const q =
          mode === "coding" ? new URLSearchParams({ topic, feedback }) : new URLSearchParams({ project: projectId, feedback });
        router.push(`/${mode}?${q}`);
      }}
    >
      <h3 id="dlg-title">New {label}</h3>
      <fieldset className="dlg-seg">
        <legend>Interview</legend>
        {/* the cobalt pill slides to the chosen option (--i is its index) */}
        <div className="dlg-track" style={{ "--i": MODES.findIndex(([v]) => v === mode) } as CSSProperties}>
          <span className="dlg-pill" aria-hidden />
          {MODES.map(([v, name]) => (
            <label key={v} className={mode === v ? "is-on" : undefined}>
              <input type="radio" name="mode" value={v} checked={mode === v} onChange={() => setMode(v)} />
              {name}
            </label>
          ))}
        </div>
      </fieldset>
      <AnimatePresence mode="wait" initial={false}>
      {mode === "coding" ? (
        <m.label key="topic" className="dlg-field" {...fieldMotion}>
          <span>Topic</span>
          <input
            name="topic"
            autoComplete="off"
            spellCheck={false}
            placeholder="Graphs, heaps, two pointers…"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
          />
        </m.label>
      ) : (
        <m.label key="project" className="dlg-field" {...fieldMotion}>
          <span>Project</span>
          <select name="project" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            {SAMPLES.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} (sample, {p.loc} lines)
              </option>
            ))}
          </select>
        </m.label>
      )}
      </AnimatePresence>
      <fieldset className="dlg-seg">
        <legend>Feedback</legend>
        <div className="dlg-track" style={{ "--i": feedback === "active" ? 0 : 1 } as CSSProperties}>
          <span className="dlg-pill" aria-hidden />
          {(["active", "passive"] as const).map((f) => (
            <label key={f} className={feedback === f ? "is-on" : undefined}>
              <input
                type="radio"
                name="feedback"
                value={f}
                checked={feedback === f}
                onChange={() => setFeedback(f)}
              />
              {f === "active" ? "Active: steps in" : "Passive: only watches"}
            </label>
          ))}
        </div>
      </fieldset>
      <button type="submit" className="ui-btn ui-btn-primary dlg-go">
        Start {label}
      </button>
    </form>
  );
}
