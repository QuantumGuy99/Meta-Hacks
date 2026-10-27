"use client";

import { useEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";

// Live chaos-lab chart on uPlot: canvas, no tweening, cheap to update many times a second.
// Fed by a synthetic stream until the backend's defense.chaos.metric messages exist.

export type LoadMode = "broke" | "held";

const COLORS = { broke: "#e5484d", held: "#4cc77a", rps: "#1c80ba", grid: "#222226", axis: "#a2a2a8" };
const WINDOW = 80; // points kept on screen
const TICK_MS = 250;

function sample(mode: LoadMode, i: number, prev: number) {
  // Broken app: p95 climbs and jitters as the race condition piles up; fixed app stays flat.
  const target = mode === "broke" ? 180 + Math.min(i, 60) * 4 : 38;
  const jitter = mode === "broke" ? 40 : 4;
  return Math.max(10, prev + (target - prev) * 0.15 + (Math.random() - 0.5) * jitter);
}

export function LiveLoadChart({
  mode,
  height = 140,
  showRps = false,
  label = "p95 latency (ms)",
}: {
  mode: LoadMode;
  height?: number;
  showRps?: boolean;
  label?: string;
}) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Seed a full window so the chart never starts empty.
    const xs: number[] = [];
    const p95: number[] = [];
    const rps: number[] = [];
    let last = mode === "broke" ? 120 : 40;
    for (let i = 0; i < WINDOW; i++) {
      xs.push(i);
      last = sample(mode, i, last);
      p95.push(last);
      rps.push(mode === "broke" ? 520 + Math.random() * 80 : 640 + Math.random() * 30);
    }

    const series: uPlot.Series[] = [
      {},
      { label, stroke: COLORS[mode], width: 2, fill: `${COLORS[mode]}1f`, points: { show: false } },
    ];
    const data: uPlot.AlignedData = showRps ? [xs, p95, rps] : [xs, p95];
    if (showRps) series.push({ label: "requests/s", stroke: COLORS.rps, width: 1.5, scale: "rps", points: { show: false } });

    // Canvas can't read CSS variables, so the axis font is a plain family list.
    const axis = (scale = "y"): uPlot.Axis => ({
      scale,
      stroke: COLORS.axis,
      grid: { stroke: COLORS.grid, width: 1 },
      ticks: { show: false },
      font: "12px system-ui, sans-serif",
      size: 44,
    });

    const plot = new uPlot(
      {
        width: el.clientWidth,
        height,
        legend: { show: false },
        cursor: { show: false },
        scales: { x: { time: false }, y: { range: [0, mode === "broke" ? 520 : 120] }, rps: { range: [0, 800] } },
        axes: [{ show: false }, axis(), ...(showRps ? [{ ...axis("rps"), side: 1, grid: { show: false } }] : [])],
        series,
      },
      data,
      el,
    );

    const ro = new ResizeObserver(() => plot.setSize({ width: el.clientWidth, height }));
    ro.observe(el);

    // Stream only while visible, and never for reduced motion (the seeded window stays).
    let visible = false;
    const io = new IntersectionObserver(([e]) => (visible = e.isIntersecting));
    io.observe(el);
    let i = WINDOW;
    const id = reduce
      ? undefined
      : window.setInterval(() => {
          if (!visible || document.hidden) return;
          xs.push(i);
          xs.shift();
          last = sample(mode, i, last);
          p95.push(last);
          p95.shift();
          rps.push(mode === "broke" ? 520 + Math.random() * 80 : 640 + Math.random() * 30);
          rps.shift();
          i++;
          plot.setData(showRps ? [xs, p95, rps] : [xs, p95]);
        }, TICK_MS);

    return () => {
      window.clearInterval(id);
      io.disconnect();
      ro.disconnect();
      plot.destroy();
    };
  }, [mode, height, showRps, label]);

  return <div ref={host} className="live-chart" role="img" aria-label={`${label}, ${mode === "broke" ? "rising under load" : "flat under load"}`} />;
}
