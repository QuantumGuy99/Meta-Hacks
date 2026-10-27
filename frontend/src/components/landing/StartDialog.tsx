"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { levelLabel, problem, project } from "@/lib/fixtures";
import type { FeedbackLevel, Mode } from "@/types/contracts";

const MODES: [Mode, string][] = [
  ["coding", "Coding Interview"],
  ["defense", "Project Defense"],
];

// Sample projects a defense can start from until upload lands (the fixture's bank-transfer).
const SAMPLES = [project];

// One dialog for both modes, so neither reads as the secondary option.
export function StartDialog() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("coding");
  const [topic, setTopic] = useState(levelLabel(problem.topics[0] ?? ""));
  const [projectId, setProjectId] = useState(SAMPLES[0].id);
  const [feedback, setFeedback] = useState<FeedbackLevel>("active");
  const label = MODES.find(([m]) => m === mode)![1];

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
        {MODES.map(([m, name]) => (
          <label key={m} className={mode === m ? "is-on" : undefined}>
            <input type="radio" name="mode" value={m} checked={mode === m} onChange={() => setMode(m)} />
            {name}
          </label>
        ))}
      </fieldset>
      {mode === "coding" ? (
        <label className="dlg-field">
          <span>Topic</span>
          <input
            name="topic"
            autoComplete="off"
            spellCheck={false}
            placeholder="Graphs, heaps, two pointers…"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
          />
        </label>
      ) : (
        <label className="dlg-field">
          <span>Project</span>
          <select name="project" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            {SAMPLES.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} (sample, {p.loc} lines)
              </option>
            ))}
          </select>
        </label>
      )}
      <fieldset className="dlg-seg">
        <legend>Feedback</legend>
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
      </fieldset>
      <button type="submit" className="ui-btn ui-btn-primary dlg-go">
        Start {label}
      </button>
    </form>
  );
}
