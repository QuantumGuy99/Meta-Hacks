"use client";

import { AnimatePresence, m } from "motion/react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { api } from "@/lib/api";
import { levelLabel } from "@/lib/fixtures";
import type { FeedbackLevel, Mode, ProblemSummary, Project } from "@/types/contracts";

const MODES: [Mode, string][] = [
  ["coding", "Coding Interview"],
  ["defense", "Project Defense"],
];

// The field under the mode switch swaps with a short cross-fade.
const fieldMotion = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4 },
  transition: { duration: 0.2, ease: [0.23, 1, 0.32, 1] as const },
};

// One dialog for both modes, so neither reads as the secondary option. Topics and projects come from the
// server (GET /api/problems and /api/defense/samples); if it can't be reached, the setup page says so.
export function StartDialog() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("coding");
  const [problems, setProblems] = useState<ProblemSummary[] | null>(null);
  const [samples, setSamples] = useState<Project[] | null>(null);
  const [offline, setOffline] = useState(false);
  const [topic, setTopic] = useState("");
  const [projectId, setProjectId] = useState("");
  const [feedback, setFeedback] = useState<FeedbackLevel>("active");
  const label = MODES.find(([v]) => v === mode)![1];

  useEffect(() => {
    let live = true;
    Promise.all([api.problems(), api.samples()])
      .then(([p, s]) => {
        if (!live) return;
        setProblems(p);
        setSamples(s);
        setProjectId((id) => id || s[0]?.id || "");
      })
      .catch(() => live && setOffline(true));
    return () => {
      live = false;
    };
  }, []);

  const topics = useMemo(() => [...new Set((problems ?? []).flatMap((p) => p.topics))].sort(), [problems]);
  const loading = !offline && (problems === null || samples === null);

  return (
    <form
      data-ui
      className="dlg"
      aria-labelledby="dlg-title"
      onSubmit={(e) => {
        e.preventDefault();
        const q =
          mode === "coding"
            ? new URLSearchParams({ ...(topic ? { topic } : {}), feedback })
            : new URLSearchParams({ ...(projectId ? { project: projectId } : {}), feedback });
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
            <select name="topic" value={topic} onChange={(e) => setTopic(e.target.value)} disabled={loading}>
              <option value="">{loading ? "Loading topics…" : "Any topic"}</option>
              {topics.map((t) => (
                <option key={t} value={t}>
                  {levelLabel(t)}
                </option>
              ))}
            </select>
          </m.label>
        ) : (
          <m.label key="project" className="dlg-field" {...fieldMotion}>
            <span>Project</span>
            <select name="project" value={projectId} onChange={(e) => setProjectId(e.target.value)} disabled={loading || !samples?.length}>
              {loading && <option value="">Loading sample apps…</option>}
              {!loading && !samples?.length && <option value="">{offline ? "Pick one on the next page" : "No sample apps yet"}</option>}
              {samples?.map((p) => (
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
      {offline && <p className="dlg-note">Can&apos;t reach the Ares server right now. You can still continue to setup.</p>}
      <button type="submit" className="ui-btn ui-btn-primary dlg-go">
        Start {label}
      </button>
    </form>
  );
}
