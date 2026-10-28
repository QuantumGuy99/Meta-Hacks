"use client";

import NumberFlow from "@number-flow/react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Bar, BarChart, LabelList, XAxis, YAxis } from "recharts";
import { ChartContainer, type ChartConfig } from "@/components/ui/chart";
import { Slider } from "@/components/ui/slider";
import { HeadlineReveal } from "@/components/motion/HeadlineReveal";
import { CodeEditor } from "@/components/room/CodeEditor";
import { clock, dimensionLabel } from "@/lib/fixtures";
import { codeAt } from "@/lib/replay";
import type { Moment, Report, TimelineEvent } from "@/types/contracts";

// Report + replay (FE-7, PLAN §14.5): scores, moments and metrics from a Report, and a replay of the session's
// timeline. The code pane is codeAt (lib/replay.ts) at the scrubber's time. The demo and the live report
// (/report/[id]) both render this.

export type ReportLine = { t: number; who: "Interviewer" | "You"; text: string };
export type ReportMark = { t: number; kind: Moment["kind"] | "run"; title: string; detail: string };

const chartConfig = { score: { label: "Score", color: "#2f6bff" } } satisfies ChartConfig;
const SPEEDS = [1, 4, 16];

export function ReportView({
  title,
  crumb,
  report,
  replay,
  file,
  transcript,
  marks,
  children,
}: {
  title: string;
  crumb: string;
  report: Report;
  /** timeline events with the file's snapshots and edits (t in ms) */
  replay: TimelineEvent[];
  file: string;
  transcript: ReportLine[];
  marks: ReportMark[];
  /** mode-specific sections under the metrics (defense: findings, attacks, verdict) */
  children?: ReactNode;
}) {
  const metrics = report.metrics;
  const duration = Math.max(1, Math.ceil(Math.max(metrics.duration_s, ...transcript.map((l) => l.t), ...marks.map((mk) => mk.t))));
  const dimensions = useMemo(
    () => report.dimensions.map((d) => ({ name: dimensionLabel(d.name), score: d.score, evidence: d.evidence })),
    [report],
  );
  const tiles: [label: string, value: number, suffix: string][] = [
    ["Duration", Math.round(metrics.duration_s / 60), " min"],
    ...(report.mode === "coding"
      ? ([
          ["Runs", metrics.runs, ""],
          ["Hidden tests", metrics.hidden_passed ?? 0, ` of ${metrics.hidden_total ?? 0}`],
        ] as [string, number, string][])
      : ([["Attacks", report.defense?.chaos_runs.length ?? 0, ""]] as [string, number, string][])),
    ["Nudges", metrics.interventions_shown, ""],
    ["Talk time", Math.round(metrics.talk_time_s / 60), " min"],
    ["Longest silence", Math.round(metrics.longest_silence_s / 60), " min"],
  ];

  const [overall, setOverall] = useState(0);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(16);
  const transcriptRef = useRef<HTMLOListElement>(null);

  // Roll the overall score up once on load.
  useEffect(() => {
    const id = requestAnimationFrame(() => setOverall(report.overall));
    return () => cancelAnimationFrame(id);
  }, [report.overall]);

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
      tRef.current = Math.min(duration, tRef.current + ((now - last) / 1000) * speed);
      last = now;
      setT(tRef.current);
      if (tRef.current >= duration) {
        setPlaying(false);
        return;
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, duration]);

  const code = useMemo(() => codeAt(replay, file, t * 1000), [replay, file, t]);
  const currentLine = transcript.reduce((idx, line, i) => (line.t <= t ? i : idx), -1);

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
        <span className="rp-crumb">{crumb}</span>
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
              {title}
            </HeadlineReveal>
            <p>{report.summary}</p>
            {(report.strengths.length > 0 || report.improvements.length > 0) && (
              <div className="rp-lists">
                {(
                  [
                    ["Strengths", report.strengths],
                    ["Improve", report.improvements],
                  ] as const
                ).map(([heading, items]) =>
                  items.length ? (
                    <div key={heading}>
                      <h2>{heading}</h2>
                      <ul>
                        {items.map((s) => (
                          <li key={s}>{s}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null,
                )}
              </div>
            )}
          </div>
          <div className="rp-chart" data-ui>
            <h2>Dimensions</h2>
            <ChartContainer config={chartConfig} className="rp-chart-box">
              <BarChart data={dimensions} layout="vertical" margin={{ left: 8, right: 28 }} accessibilityLayer>
                <XAxis type="number" domain={[0, 10]} hide />
                <YAxis type="category" dataKey="name" width={120} tickLine={false} axisLine={false} tick={{ fill: "#b4b4bc", fontSize: 13 }} />
                <Bar dataKey="score" fill="var(--color-score)" radius={2} barSize={14} isAnimationActive={false}>
                  <LabelList dataKey="score" position="right" fill="#f2f2f0" fontSize={13} />
                </Bar>
              </BarChart>
            </ChartContainer>
            <dl className="rp-evidence">
              {dimensions.map((d) => (
                <div key={d.name}>
                  <dt>{d.name}</dt>
                  <dd>{d.evidence}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <dl className="rp-metrics fr-metrics">
          {tiles.map(([label, value, suffix]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>
                <NumberFlow value={value} suffix={suffix} />
              </dd>
            </div>
          ))}
        </dl>

        {children}

        <section className="rp-replay" aria-labelledby="rp-replay-title">
          <div className="rp-replay-head">
            <h2 id="rp-replay-title">Replay</h2>
            <div className="rp-controls">
              <button type="button" className="ui-btn ui-btn-primary" onClick={() => (t >= duration ? (setT(0), setPlaying(true)) : setPlaying((p) => !p))}>
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
                {clock(t)} / {clock(duration)}
              </span>
            </div>
          </div>

          <div className="rp-scrub">
            <Slider
              value={[t]}
              min={0}
              max={duration}
              step={1}
              thumbLabel="Replay position"
              onValueChange={(v) => seek(Array.isArray(v) ? v[0] : (v as number))}
            />
            <div className="rp-markers">
              {marks.map((mo, i) => (
                <button
                  key={`${mo.t}-${i}`}
                  type="button"
                  className={`rp-marker mk-${mo.kind}`}
                  style={{ left: `${(mo.t / duration) * 100}%` }}
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
              {transcript.map((line, i) => (
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
            {marks.map((mo, i) => (
              <li key={`${mo.t}-${i}`}>
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
