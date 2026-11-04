"use client";

import { useEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import type { ChaosRun } from "@/types/contracts";

// Chaos-lab chart on uPlot (canvas, no tweening). It replays one ChaosRun: the run's own metric
// samples are the anchors, and the points between them are filled in so a 10 s attack reads as
// a line. Live sessions will append defense.chaos.metric samples instead.

export type LoadMetric = "p95" | "violations";

const COLORS = { broke: "#ffffff", held: "#2f6bff", error: "#8fb3ff", rps: "#8fb3ff", grid: "#1c1c20", axis: "#b4b4bc" };
const POINTS = 40; // one every 250 ms over a 10 s run
const TICK_MS = 250;

// Small deterministic wobble so the replay looks the same on every load.
const wobble = (i: number) => Math.sin(i * 12.9898) * 0.5 + Math.sin(i * 4.1414) * 0.5;

function series(run: ChaosRun) {
  const last = run.metrics[run.metrics.length - 1];
  const first = run.metrics[0];
  const xs: number[] = [];
  const p95: number[] = [];
  const rps: number[] = [];
  const violations: number[] = [];
  for (let i = 0; i < POINTS; i++) {
    const f = i / (POINTS - 1);
    // ease from the first sample to the last, then hold there with a little jitter
    const k = Math.min(1, f * 4);
    xs.push(i * (TICK_MS / 1000));
    p95.push(first.p95_ms + (last.p95_ms - first.p95_ms) * k + wobble(i) * last.p95_ms * 0.06);
    rps.push(first.rps + (last.rps - first.rps) * k + wobble(i + 7) * last.rps * 0.04);
    violations.push(Math.round(last.violations * f));
  }
  return { xs, p95, rps, violations };
}

export function LiveLoadChart({
  run,
  compare,
  metric = "p95",
  height = 140,
  showRps = false,
  ink,
}: {
  run: ChaosRun;
  /** an earlier run drawn underneath, dashed, for before/after (verify over baseline) */
  compare?: ChaosRun;
  metric?: LoadMetric;
  height?: number;
  showRps?: boolean;
  /** draw everything in this one colour (e.g. black on a bright card) */
  ink?: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const label = metric === "p95" ? "p95 latency (ms)" : "invariant violations";

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const full = series(run);
    const values = metric === "p95" ? full.p95 : full.violations;
    const before = compare ? series(compare) : null;
    const beforeValues = before ? (metric === "p95" ? before.p95 : before.violations) : null;
    const color = ink ?? COLORS[run.verdict];

    const series_: uPlot.Series[] = [
      {},
      { label, stroke: color, width: 2, fill: `${color}1f`, points: { show: false } },
    ];
    if (showRps) series_.push({ label: "requests/s", stroke: COLORS.rps, width: 1.5, scale: "rps", points: { show: false } });
    if (beforeValues) series_.push({ label: `${label}, before`, stroke: COLORS.axis, width: 1.5, dash: [5, 4], points: { show: false } });

    // Canvas can't read CSS variables, so the axis font is a plain family list.
    const axis = (scale = "y"): uPlot.Axis => ({
      scale,
      stroke: ink ?? COLORS.axis,
      grid: { stroke: ink ? `${ink}26` : COLORS.grid, width: 1 },
      ticks: { show: false },
      font: "12px system-ui, sans-serif",
      size: 44,
    });

    const peak = Math.max(run.metrics.at(-1)!.violations, compare?.metrics.at(-1)!.violations ?? 0);
    const top = metric === "p95" ? 200 : Math.max(10, Math.ceil((peak * 1.25) / 10) * 10);
    // Replay from the first point unless motion is reduced, then show the whole run.
    let shown = reduce ? POINTS : 1;
    // The earlier run is already over, so it shows in full while this one replays over it.
    const slice = (): uPlot.AlignedData => {
      const xs = full.xs;
      const cut = (v: number[]) => v.map((y, i) => (i < shown ? y : null));
      const data: (number | null)[][] = [cut(values)];
      if (showRps) data.push(cut(full.rps));
      if (beforeValues) data.push(beforeValues);
      return [xs, ...data] as uPlot.AlignedData;
    };

    const plot = new uPlot(
      {
        width: el.clientWidth,
        height,
        legend: { show: false },
        cursor: { show: false },
        scales: { x: { time: false, range: [0, full.xs[POINTS - 1]] }, y: { range: [0, top] }, rps: { range: [0, 600] } },
        axes: [{ show: false }, axis(), ...(showRps ? [{ ...axis("rps"), side: 1, grid: { show: false } }] : [])],
        series: series_,
      },
      slice(),
      el,
    );

    const ro = new ResizeObserver(() => plot.setSize({ width: el.clientWidth, height }));
    ro.observe(el);

    // Play the run once it scrolls into view.
    let id: number | undefined;
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting || id !== undefined || shown >= POINTS) return;
      id = window.setInterval(() => {
        if (document.hidden) return;
        shown = Math.min(POINTS, shown + 1);
        plot.setData(slice());
        if (shown >= POINTS) window.clearInterval(id);
      }, TICK_MS);
    });
    io.observe(el);

    return () => {
      window.clearInterval(id);
      io.disconnect();
      ro.disconnect();
      plot.destroy();
    };
  }, [run, compare, metric, height, showRps, label, ink]);

  const end = metric === "p95" ? `ends near ${Math.round(run.metrics.at(-1)!.p95_ms)} ms` : `reaches ${run.metrics.at(-1)!.violations}`;
  return <div ref={host} className="live-chart" role="img" aria-label={`${label} over the ${run.kind} run, ${end}`} />;
}
