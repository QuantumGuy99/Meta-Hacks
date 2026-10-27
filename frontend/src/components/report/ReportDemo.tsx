"use client";

import NumberFlow from "@number-flow/react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, LabelList, XAxis, YAxis } from "recharts";
import { ChartContainer, type ChartConfig } from "@/components/ui/chart";
import { Slider } from "@/components/ui/slider";
import { HeadlineReveal } from "@/components/motion/HeadlineReveal";
import { CodeEditor } from "@/components/room/CodeEditor";
import { codeAt } from "@/lib/replay";
import {
  analysis,
  CLARIFY_QUESTION,
  clock,
  codingReport,
  dimensionLabel,
  DRAFT_CODE,
  FIXED_CODE,
  nudge,
  problem,
  tabFlag,
  transcript,
  visibleRun,
  WRAP_UP_QUESTION,
} from "@/lib/fixtures";
import type { EditorEvent, Moment, TimelineEvent } from "@/types/contracts";

// Report + replay demo (FE-7 shape) for the shared Quiet Streak session: scores, moments and
// metrics come from the report fixture. The code pane replays a timeline of editor events through the
// shared codeAt (lib/replay.ts), the same function the real report will use.

const report = codingReport;
const metrics = report.metrics;
const DURATION = metrics.duration_s;
const sec = (ms: number) => Math.round(ms / 1000);

const DIMENSIONS = report.dimensions.map((d) => ({ name: dimensionLabel(d.name), score: d.score, evidence: d.evidence }));
const chartConfig = { score: { label: "Score", color: "#2f6bff" } } satisfies ChartConfig;

type Kind = Moment["kind"] | "run";
type Mark = { t: number; kind: Kind; title: string; detail: string };

// Report moments, plus the timeline's run and integrity events as extra markers.
const MARKS: Mark[] = [
  ...report.moments.map((mo) => ({ t: sec(mo.t), kind: mo.kind, title: mo.title, detail: mo.tip ? `${mo.detail} ${mo.tip}` : mo.detail })),
  {
    t: sec(visibleRun.t),
    kind: "run" as const,
    title: `Run 1: ${visibleRun.passed} of ${visibleRun.total}`,
    detail: "Visible tests pass.",
  },
  { t: sec(tabFlag.t), kind: "integrity" as const, title: "Noted", detail: tabFlag.detail },
].sort((a, b) => a.t - b.t);

const FILE = "solution.py";

/** One Monaco-style change turning `a` into `b` (common prefix and suffix kept). */
function change(a: string, b: string) {
  let pre = 0;
  while (pre < a.length && pre < b.length && a[pre] === b[pre]) pre++;
  let suf = 0;
  while (suf < a.length - pre && suf < b.length - pre && a[a.length - 1 - suf] === b[b.length - 1 - suf]) suf++;
  return { range_offset: pre, range_length: a.length - pre - suf, text: b.slice(pre, b.length - suf) };
}

// The session's code over time: the starter code, the draft growing a few lines at a time from the first
// edit (time_to_first_edit_s), and the trailing-streak fix right after the nudge.
const draftLines = DRAFT_CODE.split("\n");
const upTo = (n: number) => draftLines.slice(0, n).join("\n") + "\n";
const STATES: [t: number, code: string][] = [
  [metrics.time_to_first_edit_s ?? 131, upTo(2)],
  [175, upTo(3)],
  [205, upTo(5)],
  [245, upTo(8)],
  [300, DRAFT_CODE],
  [sec(nudge.t) + 48, FIXED_CODE],
];
const REPLAY: TimelineEvent[] = [
  { seq: 1, t: 0, kind: "snapshot", payload: { t: 0, file: FILE, version: 1, code: problem.starter_code } },
];
STATES.reduce((prev, [t, code], i) => {
  const edit: EditorEvent = { t: t * 1000, file: FILE, version: i + 2, kind: "change", changes: [change(prev, code)] };
  REPLAY.push({ seq: i + 2, t: t * 1000, kind: "editor", payload: edit as unknown as TimelineEvent["payload"] });
  return code;
}, problem.starter_code);

type Line = { t: number; who: "Interviewer" | "You"; text: string };
const LINES: Line[] = [
  { t: 60, who: "You", text: CLARIFY_QUESTION },
  { t: 66, who: "Interviewer", text: "No. Quiet means strictly below the threshold." },
  ...transcript.map((turn) => ({
    t: sec(turn.end_ms),
    who: turn.speaker === "candidate" ? ("You" as const) : ("Interviewer" as const),
    text: turn.text,
  })),
  { t: 110, who: "You", text: analysis.stated_plan ?? "" },
  { t: sec(nudge.t), who: "Interviewer", text: nudge.text },
  { t: 1010, who: "Interviewer", text: WRAP_UP_QUESTION },
  { t: 1018, who: "You", text: "O(n) time and O(1) space, one pass with a counter." },
];
const TRANSCRIPT = LINES.sort((a, b) => a.t - b.t);

const TILES: [label: string, value: number, suffix: string][] = [
  ["Duration", Math.round(DURATION / 60), " min"],
  ["Runs", metrics.runs, ""],
  ["Hidden tests", metrics.hidden_passed ?? 0, ` of ${metrics.hidden_total ?? 0}`],
  ["Nudges", metrics.interventions_shown, ""],
  ["Talk time", Math.round(metrics.talk_time_s / 60), " min"],
  ["Longest silence", Math.round(metrics.longest_silence_s / 60), " min"],
];

const SPEEDS = [1, 4, 16];

export function ReportDemo() {
  const [overall, setOverall] = useState(0);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(16);
  const transcriptRef = useRef<HTMLOListElement>(null);

  // Roll the overall score up once on load.
  useEffect(() => {
    const id = requestAnimationFrame(() => setOverall(report.overall));
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

  const code = useMemo(() => codeAt(REPLAY, FILE, t * 1000), [t]);
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

  const seek = (to: number) => {
    setPlaying(false);
    setT(to);
  };

  return (
    <div className="rp">
      <header className="rm-top">
        <Link href="/" className="rm-brand" translate="no">
          Ares
        </Link>
        <span className="rp-crumb">Report · {problem.title} · Demo</span>
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
            <HeadlineReveal as="h1" id="rp-title" onLoad>
              {problem.title}
            </HeadlineReveal>
            <p>{report.summary}</p>
            <div className="rp-lists">
              <div>
                <h2>Strengths</h2>
                <ul>
                  {report.strengths.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h2>Improve</h2>
                <ul>
                  {report.improvements.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
          <div className="rp-chart" data-ui>
            <h2>Dimensions</h2>
            <ChartContainer config={chartConfig} className="rp-chart-box">
              <BarChart data={DIMENSIONS} layout="vertical" margin={{ left: 8, right: 28 }} accessibilityLayer>
                <XAxis type="number" domain={[0, 10]} hide />
                <YAxis type="category" dataKey="name" width={120} tickLine={false} axisLine={false} tick={{ fill: "#b4b4bc", fontSize: 13 }} />
                <Bar dataKey="score" fill="var(--color-score)" radius={2} barSize={14} isAnimationActive={false}>
                  <LabelList dataKey="score" position="right" fill="#f2f2f0" fontSize={13} />
                </Bar>
              </BarChart>
            </ChartContainer>
            <dl className="rp-evidence">
              {DIMENSIONS.map((d) => (
                <div key={d.name}>
                  <dt>{d.name}</dt>
                  <dd>{d.evidence}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <dl className="rp-metrics fr-metrics">
          {TILES.map(([label, value, suffix]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>
                <NumberFlow value={value} suffix={suffix} />
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
              onValueChange={(v) => seek(Array.isArray(v) ? v[0] : (v as number))}
            />
            <div className="rp-markers">
              {MARKS.map((mo) => (
                <button
                  key={mo.t}
                  type="button"
                  className={`rp-marker mk-${mo.kind}`}
                  style={{ left: `${(mo.t / DURATION) * 100}%` }}
                  onClick={() => seek(mo.t)}
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
            {MARKS.map((mo) => (
              <li key={mo.t}>
                <button type="button" className={`rp-moment mk-${mo.kind}`} onClick={() => seek(mo.t)}>
                  <span className="df-muted rp-moment-time">{clock(mo.t)}</span>
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
