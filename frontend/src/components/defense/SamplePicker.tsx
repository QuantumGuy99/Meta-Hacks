"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type CSSProperties } from "react";
import { api, errorText } from "@/lib/api";
import type { FeedbackLevel, Project } from "@/types/contracts";

// /defense: pick a sample app (zip upload is P1), then POST /api/sessions and open the defense.
// Pre-selects the ?project= the landing page's start dialog sends.
export function SamplePicker() {
  const router = useRouter();
  const params = useSearchParams();
  const [samples, setSamples] = useState<Project[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [projectId, setProjectId] = useState("");
  const [feedback, setFeedback] = useState<FeedbackLevel>(params.get("feedback") === "passive" ? "passive" : "active");
  const [voice, setVoice] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .samples()
      .then((list) => {
        if (!live) return;
        setSamples(list);
        const wanted = params.get("project");
        setProjectId(list.find((p) => p.id === wanted)?.id ?? list[0]?.id ?? "");
      })
      .catch((err) => live && setLoadError(errorText(err)));
    return () => {
      live = false;
    };
  }, [params]);

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      const session = await api.createSession({ mode: "defense", project_id: projectId, feedback, voice });
      router.push(`/defense/${session.id}`);
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
      <h1 id="setup-title">New Project Defense</h1>
      {loadError && (
        <p className="setup-error" role="alert">
          {loadError}
        </p>
      )}
      {samples && samples.length === 0 && (
        <p className="setup-error" role="alert">
          The server has no sample apps yet. Point DEFENSE_EXTRA_APPS_DIR at backend/tests/fixtures/apps, or add apps
          under data/defense_apps.
        </p>
      )}
      <fieldset className="setup-cards">
        <legend>Project</legend>
        {(samples ?? []).map((p) => (
          <label key={p.id} className={projectId === p.id ? "setup-card is-on" : "setup-card"}>
            <input type="radio" name="project" value={p.id} checked={projectId === p.id} onChange={() => setProjectId(p.id)} />
            <strong translate="no">{p.name}</strong>
            <span>
              Sample · {p.loc} lines · {p.files.length} files
            </span>
          </label>
        ))}
        {!samples && !loadError && <p className="live-empty">Loading sample apps…</p>}
      </fieldset>
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
          Speech to text: answer the grill with the microphone
        </label>
      </div>
      {error && (
        <p className="setup-error" role="alert">
          {error}
        </p>
      )}
      <button type="submit" className="ui-btn ui-btn-primary dlg-go" disabled={starting || !projectId}>
        {starting ? "Starting…" : "Start Project Defense"}
      </button>
      <Link href="/defense/demo" className="setup-alt">
        Or try the scripted defense demo
      </Link>
    </form>
  );
}
