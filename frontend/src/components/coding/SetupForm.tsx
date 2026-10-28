"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { api, errorText } from "@/lib/api";
import { levelLabel } from "@/lib/fixtures";
import type { Difficulty, FeedbackLevel, ProblemSummary } from "@/types/contracts";

const DIFFICULTIES: (Difficulty | "any")[] = ["any", "easy", "medium", "hard"];

// /coding: pick a problem (or a difficulty and topic), feedback and voice, then POST /api/sessions and open the
// room. Pre-fills from the ?topic=&feedback= the landing page's start dialog sends.
export function SetupForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [problems, setProblems] = useState<ProblemSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [slug, setSlug] = useState("");
  // ?difficulty= comes from the guide's "start a coding interview" suggestion (#51)
  const [difficulty, setDifficulty] = useState<Difficulty | "any">(() => {
    const d = params.get("difficulty");
    return d === "easy" || d === "medium" || d === "hard" ? d : "any";
  });
  const [topic, setTopic] = useState("");
  const [feedback, setFeedback] = useState<FeedbackLevel>(params.get("feedback") === "passive" ? "passive" : "active");
  const [voice, setVoice] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .problems()
      .then((list) => {
        if (!live) return;
        setProblems(list);
        // The landing dialog's topic is free text: keep it only if a problem has that topic.
        const wanted = params.get("topic")?.trim().toLowerCase();
        const known = list.flatMap((p) => p.topics);
        if (wanted && known.includes(wanted)) setTopic(wanted);
      })
      .catch((err) => live && setLoadError(errorText(err)));
    return () => {
      live = false;
    };
  }, [params]);

  const topics = useMemo(() => [...new Set((problems ?? []).flatMap((p) => p.topics))].sort(), [problems]);
  const picked = problems?.find((p) => p.slug === slug) ?? null;

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      const session = await api.createSession({
        mode: "coding",
        feedback,
        voice,
        speak_replies: false, // voice is speech to text only: the interviewer's replies stay text
        problem_slug: slug || null,
        difficulty: slug || difficulty === "any" ? null : difficulty,
        topic: slug || !topic ? null : topic,
      });
      router.push(`/coding/${session.id}`);
    } catch (err) {
      setError(errorText(err));
      setStarting(false);
    }
  };

  return (
    <form
      data-ui
      className="dlg setup"
      aria-labelledby="setup-title"
      onSubmit={(e) => {
        e.preventDefault();
        void start();
      }}
    >
      <h1 id="setup-title">New Coding Interview</h1>
      {loadError && (
        <p className="setup-error" role="alert">
          {loadError}
        </p>
      )}
      <label className="dlg-field">
        <span>Problem</span>
        <select name="problem" value={slug} onChange={(e) => setSlug(e.target.value)} disabled={!problems}>
          <option value="">{problems ? "Any problem (picked for you)" : "Loading problems…"}</option>
          {problems?.map((p) => (
            <option key={p.slug} value={p.slug}>
              {p.title} · {levelLabel(p.difficulty)}
            </option>
          ))}
        </select>
      </label>
      {!picked && (
        <>
          <fieldset className="dlg-seg">
            <legend>Difficulty</legend>
            <div className="dlg-track setup-track-4" style={{ "--i": DIFFICULTIES.indexOf(difficulty) } as CSSProperties}>
              <span className="dlg-pill" aria-hidden />
              {DIFFICULTIES.map((d) => (
                <label key={d} className={difficulty === d ? "is-on" : undefined}>
                  <input type="radio" name="difficulty" value={d} checked={difficulty === d} onChange={() => setDifficulty(d)} />
                  {levelLabel(d)}
                </label>
              ))}
            </div>
          </fieldset>
          <label className="dlg-field">
            <span>Topic</span>
            <select name="topic" value={topic} onChange={(e) => setTopic(e.target.value)} disabled={!problems}>
              <option value="">Any topic</option>
              {topics.map((t) => (
                <option key={t} value={t}>
                  {levelLabel(t)}
                </option>
              ))}
            </select>
          </label>
        </>
      )}
      <fieldset className="dlg-seg">
        <legend>Feedback</legend>
        <div className="dlg-track" style={{ "--i": feedback === "active" ? 0 : 1 } as CSSProperties}>
          <span className="dlg-pill" aria-hidden />
          {(["active", "passive"] as const).map((f) => (
            <label key={f} className={feedback === f ? "is-on" : undefined}>
              <input type="radio" name="feedback" value={f} checked={feedback === f} onChange={() => setFeedback(f)} />
              {f === "active" ? "Active: steps in" : "Passive: only watches"}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="setup-checks">
        <label>
          <input type="checkbox" checked={voice} onChange={(e) => setVoice(e.target.checked)} />
          Speech to text: talk through your approach with the microphone
        </label>
      </div>
      {error && (
        <p className="setup-error" role="alert">
          {error}
        </p>
      )}
      <button type="submit" className="ui-btn ui-btn-primary dlg-go" disabled={starting || !problems}>
        {starting ? "Starting…" : "Start Coding Interview"}
      </button>
      <Link href="/coding/demo" className="setup-alt">
        Or try the scripted demo room
      </Link>
    </form>
  );
}
