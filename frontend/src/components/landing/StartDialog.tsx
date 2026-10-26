"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Feedback = "active" | "passive";

export function StartDialog() {
  const router = useRouter();
  const [topic, setTopic] = useState("Sliding window");
  const [feedback, setFeedback] = useState<Feedback>("active");

  return (
    <form
      data-ui
      className="dlg"
      aria-labelledby="dlg-title"
      onSubmit={(e) => {
        e.preventDefault();
        const q = new URLSearchParams({ topic, feedback });
        router.push(`/coding?${q}`);
      }}
    >
      <h3 id="dlg-title">New Coding Interview</h3>
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
        Start Interview
      </button>
    </form>
  );
}
