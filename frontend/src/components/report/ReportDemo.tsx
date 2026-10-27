"use client";

import NumberFlow from "@number-flow/react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, LabelList, XAxis, YAxis } from "recharts";
import { ChartContainer, type ChartConfig } from "@/components/ui/chart";
import { Slider } from "@/components/ui/slider";
import { CodeEditor } from "@/components/room/CodeEditor";

// Report + replay demo (FE-7 shape) for a recorded coding session, on mock timeline data.

const DURATION = 31 * 60; // seconds

const DIMENSIONS = [
  { name: "Problem solving", score: 8 },
  { name: "Correctness", score: 7 },
  { name: "Code quality", score: 8 },
  { name: "Communication", score: 9 },
  { name: "Independence", score: 6 },
];

const chartConfig = { score: { label: "Score", color: "#1c80ba" } } satisfies ChartConfig;

type Kind = "milestone" | "nudge" | "run" | "hint" | "good";
type Moment = { t: number; kind: Kind; title: string; detail: string };

const MOMENTS: Moment[] = [
  { t: 72, kind: "good", title: "Stated a plan", detail: "Sliding window with two deques, linear time." },
  { t: 410, kind: "run", title: "Run 1: 3 of 4", detail: "Empty input returned 1." },
  { t: 432, kind: "nudge", title: "Nudge on empty input", detail: "“You mentioned handling an empty list. I don’t see that yet.”" },
  { t: 610, kind: "hint", title: "Asked for a hint", detail: "Hint ladder level 1 (nudge)." },
  { t: 905, kind: "run", title: "Run 2: 4 of 4", detail: "All visible tests pass." },
  { t: 1520, kind: "milestone", title: "Submitted: 22 of 22", detail: "Hidden tests pass." },
  { t: 1700, kind: "good", title: "Wrap-up answer", detail: "Explained O(n) time, O(k) space." },
];

const SNAPSHOTS: { t: number; code: string }[] = [
  { t: 0, code: "def longest_steady_run(temps: list[int], k: int) -> int:\n    pass\n" },
  {
    t: 180,
    code: "def longest_steady_run(temps: list[int], k: int) -> int:\n    best = 1\n    left = 0\n    for right in range(len(temps)):\n        pass\n    return best\n",
  },
  {
    t: 400,
    code: "def longest_steady_run(temps: list[int], k: int) -> int:\n    best = 1\n    left = 0\n    for right in range(len(temps)):\n        window = temps[left:right + 1]\n        while max(window) - min(window) > k:\n            left += 1\n            window = temps[left:right + 1]\n        best = max(best, right - left + 1)\n    return best\n",
  },
  {
    t: 880,
    code: "def longest_steady_run(temps: list[int], k: int) -> int:\n    if not temps:\n        return 0\n    best = 1\n    left = 0\n    for right in range(len(temps)):\n        window = temps[left:right + 1]\n        while max(window) - min(window) > k:\n            left += 1\n            window = temps[left:right + 1]\n        best = max(best, right - left + 1)\n    return best\n",
  },
];

const TRANSCRIPT: { t: number; who: "Interviewer" | "You"; text: string }[] = [
  { t: 10, who: "Interviewer", text: "Read the problem, ask anything unclear, then talk me through your approach." },
  { t: 48, who: "You", text: "Can readings be negative? Is k inclusive?" },
  { t: 55, who: "Interviewer", text: "Yes to both." },
  { t: 72, who: "You", text: "Sliding window with two deques for min and max. Linear time." },
  { t: 432, who: "Interviewer", text: "You mentioned handling an empty list. I don’t see that yet." },
  { t: 610, who: "Interviewer", text: "Look at what best starts as." },
  { t: 1700, who: "Interviewer", text: "What’s the time complexity of your window?" },
  { t: 1712, who: "You", text: "O(n) amortised; each index enters and leaves each deque once." },
];

const SPEEDS = [1, 4, 16];

const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

function codeAt(t: number) {
  let code = SNAPSHOTS[0].code;
  for (const s of SNAPSHOTS) if (s.t <= t) code = s.code;
  return code;
}

export function ReportDemo() {
  const [overall, setOverall] = useState(0);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(16);
  const transcriptRef = useRef<HTMLOListElement>(null);

  // Roll the overall score up once on load.
  useEffect(() => {
    const id = requestAnimationFrame(() => setOverall(78));
    return () => cancelAnimationFrame(id);
  }, []);

  // Playback clock on requestAnimationFrame.
  const tRef = useRef(0);
  useEffect(() => {
    tRef.current = t;
  }, [t]);
  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    let raf = 0;
    const step = (now: number) => {
      tRef.current = Math.min(DURATION, tRef.current + ((now - last) / 1000) * speed);
      last = now;
      setT(tRef.current);
      if (tRef.current >= DURATION) {
        setPlaying(false);
        return;
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed]);

  const code = useMemo(() => codeAt(t), [t]);
  const currentLine = TRANSCRIPT.reduce((idx, line, i) => (line.t <= t ? i : idx), -1);

  // Keep the current transcript line in view by scrolling the list only, never the page.
  useEffect(() => {
    const list = transcriptRef.current;
    const el = list?.querySelector<HTMLElement>(`[data-i="${currentLine}"]`);
    if (!list || !el) return;
    const top = el.offsetTop;
    if (top < list.scrollTop || top + el.offsetHeight > list.scrollTop + list.clientHeight) {
      list.scrollTo({ top: top - 8, behavior: "smooth" });
    }
  }, [currentLine]);

  return (
    <div className="rp">
      <header className="rm-top">
        <Link href="/" className="rm-brand" translate="no">
          Crucible
        </Link>
        <span className="rp-crumb">Report · Longest Steady Run · Demo</span>
      </header>

      <div className="rp-body">
        <section className="rp-summary" aria-labelledby="rp-title">
          <div className="rp-overall">
            <span className="df-muted">Overall</span>
            <strong>
              <NumberFlow value={overall} />
            </strong>
          </div>
          <div className="rp-text">
            <h1 id="rp-title">Solid process, one missed edge case</h1>
            <p>
              You stated a clear plan before coding and explained your complexity well. The empty-input case slipped
              until the interviewer pointed at it, and one hint was needed to close it.
            </p>
            <div className="rp-lists">
              <div>
                <h2>Strengths</h2>
                <ul>
                  <li>Asked clarifying questions before coding</li>
                  <li>Clean sliding-window structure</li>
                  <li>Clear complexity explanation at wrap-up</li>
                </ul>
              </div>
              <div>
                <h2>Improve</h2>
                <ul>
                  <li>List edge cases before the first run</li>
                  <li>Avoid re-slicing the window each step</li>
                  <li>Talk through fixes while you type</li>
                </ul>
              </div>
            </div>
          </div>
          <div className="rp-chart" data-ui>
            <h2>Dimensions</h2>
            <ChartContainer config={chartConfig} className="rp-chart-box">
              <BarChart data={DIMENSIONS} layout="vertical" margin={{ left: 8, right: 28 }} accessibilityLayer>
                <XAxis type="number" domain={[0, 10]} hide />
                <YAxis type="category" dataKey="name" width={120} tickLine={false} axisLine={false} tick={{ fill: "#a2a2a8", fontSize: 13 }} />
                <Bar dataKey="score" fill="var(--color-score)" radius={2} barSize={14} isAnimationActive={false}>
                  <LabelList dataKey="score" position="right" fill="#f2f2f0" fontSize={13} />
                </Bar>
              </BarChart>
            </ChartContainer>
          </div>
        </section>

        <dl className="rp-metrics fr-metrics">
          {[
            ["Duration", 31, " min"],
            ["Runs", 4, ""],
            ["Hints", 1, ""],
            ["Pasted chars", 0, ""],
            ["Talk time", 9, " min"],
            ["Longest silence", 3, " min"],
          ].map(([label, value, suffix]) => (
            <div key={label as string}>
              <dt>{label}</dt>
              <dd>
                <NumberFlow value={value as number} suffix={suffix as string} />
              </dd>
            </div>
          ))}
        </dl>

        <section className="rp-replay" aria-labelledby="rp-replay-title">
          <div className="rp-replay-head">
            <h2 id="rp-replay-title">Replay</h2>
            <div className="rp-controls">
              <button type="button" className="ui-btn ui-btn-primary" onClick={() => (t >= DURATION ? (setT(0), setPlaying(true)) : setPlaying((p) => !p))}>
                {playing ? "Pause" : "Play"}
              </button>
              <div className="rp-speeds" role="group" aria-label="Playback speed">
                {SPEEDS.map((s) => (
                  <button key={s} type="button" aria-pressed={speed === s} onClick={() => setSpeed(s)}>
                    {s}×
                  </button>
                ))}
              </div>
              <span className="rp-time" aria-live="off">
                {clock(t)} / {clock(DURATION)}
              </span>
            </div>
          </div>

          <div className="rp-scrub">
            <Slider
              value={[t]}
              min={0}
              max={DURATION}
              step={1}
              thumbLabel="Replay position"
              onValueChange={(v) => {
                setPlaying(false);
                setT(Array.isArray(v) ? v[0] : (v as number));
              }}
            />
            <div className="rp-markers">
              {MOMENTS.map((mo) => (
                <button
                  key={mo.t}
                  type="button"
                  className={`rp-marker mk-${mo.kind}`}
                  style={{ left: `${(mo.t / DURATION) * 100}%` }}
                  onClick={() => {
                    setPlaying(false);
                    setT(mo.t);
                  }}
                  aria-label={`${clock(mo.t)}: ${mo.title}`}
                  title={`${clock(mo.t)} · ${mo.title}`}
                />
              ))}
            </div>
          </div>

          <div className="rp-panes">
            <div className="rp-code" data-ui>
              <CodeEditor value={code} readOnly height={300} />
            </div>
            <ol className="rp-transcript" ref={transcriptRef} aria-label="Transcript">
              {TRANSCRIPT.map((line, i) => (
                <li key={i} data-i={i} className={i === currentLine ? "is-now" : i > currentLine ? "is-future" : ""}>
                  <span className="df-muted">
                    {clock(line.t)} · {line.who}
                  </span>
                  {line.text}
                </li>
              ))}
            </ol>
          </div>

          <ul className="rp-moments" aria-label="Moments">
            {MOMENTS.map((mo) => (
              <li key={mo.t}>
                <button
                  type="button"
                  className={`rp-moment mk-${mo.kind}`}
                  onClick={() => {
                    setPlaying(false);
                    setT(mo.t);
                  }}
                >
                  <span className="df-muted">{clock(mo.t)}</span>
                  <strong>{mo.title}</strong>
                  <span>{mo.detail}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
