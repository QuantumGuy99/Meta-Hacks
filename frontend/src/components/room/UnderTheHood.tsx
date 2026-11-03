"use client";

import { useClock, type ActivityEvent } from "@/lib/session";
import type { ModelActivity } from "@/types/contracts";

// "Under the hood" (docs/STORY.md, PR #39): a slim strip along the bottom of the room with one chip per Meta
// model. A chip pulses while its model works on something, then shows what it did and how long it took, and
// dims a few seconds later. Only which model did what kind of task, never any content. In the report's
// replay it shows the same thing at the scrubber's time.

type ModelName = ModelActivity["model_name"];
type ChipState = "idle" | "working" | ModelActivity["status"];

// Always shown, in this order; Muse Spark Open only appears once it has been used (it's a fallback).
const MODELS: ModelName[] = ["Muse Spark", "Muse Wonder", "Muse Voice", "SAM 3.1", "Muse Image"];
const FRESH_MS = 6000;

const secs = (ms: number | null) => (ms === null ? "" : ms < 10_000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms / 1000)} s`);

function label(e: ModelActivity): string {
  switch (e.status) {
    case "started":
      return `${e.task}…`;
    case "done":
      return `${e.task} · ${secs(e.latency_ms)}`;
    case "cached":
      return `${e.task} · cached`;
    case "fallback":
      return `${e.task} · backup model${e.latency_ms !== null ? ` · ${secs(e.latency_ms)}` : ""}`;
    case "failed":
      return `${e.task} · didn't finish`;
    case "stopped":
      return e.task;
  }
}

/** Each model's chip at a moment: `t` (session ms) in the replay, or `now` (Date.now()) live. */
function chips(events: ActivityEvent[], at: { t: number } | { now: number }) {
  const replay = "t" in at;
  const seen = replay ? events.filter((e) => e.t <= at.t) : events;
  // The latest event per call: a call is working while its latest event is "started".
  const calls = new Map<string, ActivityEvent>();
  for (const e of seen) {
    const prev = calls.get(e.call_id);
    if (!prev || e.t >= prev.t) calls.set(e.call_id, e);
  }
  const used = new Set(seen.map((e) => e.model_name));
  const names = used.has("Muse Spark Open") ? [...MODELS.slice(0, 2), "Muse Spark Open" as const, ...MODELS.slice(2)] : MODELS;
  return names.map((name) => {
    const mine = [...calls.values()].filter((e) => e.model_name === name).sort((a, b) => a.t - b.t);
    const working = mine.filter((e) => e.status === "started");
    if (working.length) return { name, state: "working" as ChipState, text: label(working.at(-1)!), fresh: true };
    const last = mine.at(-1);
    if (!last) return { name, state: "idle" as ChipState, text: "", fresh: false };
    const age = replay ? at.t - last.t : last.wall !== undefined ? (at.now ? at.now - last.wall : 0) : Infinity;
    return { name, state: last.status as ChipState, text: label(last), fresh: age < FRESH_MS };
  });
}

export function UnderTheHood({ events, t }: { events: ActivityEvent[]; t?: number }) {
  // live: tick once a second so finished chips dim on time (only while something happened recently)
  const recent = t === undefined && events.some((e) => e.wall !== undefined);
  const now = useClock(recent);
  // before the first tick `now` is 0, so a just-arrived event counts as fresh
  const list = chips(events, t === undefined ? { now } : { t });
  return (
    <div className="uth" aria-label="Under the hood: which Meta model is working">
      <span className="uth-title">Under the hood</span>
      <ul>
        {list.map((c) => (
          <li key={c.name} className={`uth-chip is-${c.state}${c.fresh ? "" : " is-dim"}`}>
            <span className="uth-dot" aria-hidden />
            <strong translate="no">{c.name}</strong>
            {c.text && <span className="uth-task">{c.text}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
