"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, api, errorText } from "@/lib/api";
import type { ChaosRun, IntegrityFlag, Intervention, Report, RunResult, TimelineEvent, TranscriptTurn } from "@/types/contracts";
import { MODEL_ACTIVITY_KIND, type ModelActivity } from "@/types/model-activity.draft";
import { DefenseExtras } from "./DefenseExtras";
import { ReportView, type ReportLine, type ReportMark } from "./ReportView";

// /report/[id]: waits while the report is generating (202), then renders it with the session's replay.

const POLL_MS = 2000;
const sec = (ms: number) => Math.round(ms / 1000);

type Loaded = { report: Report; timeline: TimelineEvent[]; title: string; file: string };
type View =
  | { kind: "loading" }
  | { kind: "generating" }
  | { kind: "error"; message: string; back?: string } // back: the room of a session that's still live
  | ({ kind: "ready" } & Loaded);

/** The file with the most edits (defense sessions can touch several). */
function mainFile(timeline: TimelineEvent[], fallback: string): string {
  const counts = new Map<string, number>();
  for (const e of timeline) {
    const file = e.payload.file;
    if ((e.kind === "editor" || e.kind === "snapshot") && typeof file === "string") counts.set(file, (counts.get(file) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? fallback;
}

function linesOf(timeline: TimelineEvent[]): ReportLine[] {
  const lines: ReportLine[] = [];
  for (const e of timeline) {
    if (e.kind === "transcript") {
      const turn = e.payload as unknown as TranscriptTurn;
      if (turn.speaker === "candidate" && turn.final && turn.text) lines.push({ t: sec(turn.start_ms), who: "You", text: turn.text });
    } else if (e.kind === "intervention") {
      const iv = e.payload as unknown as Intervention;
      if (!iv.suppressed && iv.text) lines.push({ t: sec(iv.t), who: "Interviewer", text: iv.text });
    }
  }
  return lines.sort((a, b) => a.t - b.t);
}

function marksOf(report: Report, timeline: TimelineEvent[]): ReportMark[] {
  const marks: ReportMark[] = report.moments.map((mo) => ({
    t: sec(mo.t),
    kind: mo.kind,
    title: mo.title,
    detail: mo.tip ? `${mo.detail} ${mo.tip}` : mo.detail,
  }));
  const count = { run: 0, submit: 0 };
  for (const e of timeline) {
    if (e.kind === "run") {
      const r = e.payload as unknown as RunResult;
      count[r.kind] += 1;
      marks.push({
        t: sec(e.t),
        kind: "run",
        title: `${r.kind === "submit" ? "Submit" : "Run"} ${count[r.kind]}: ${r.passed} of ${r.total}`,
        detail: r.compile_error ? "The code didn't run." : r.passed === r.total ? "Every test passed." : `${r.total - r.passed} failed.`,
      });
    } else if (e.kind === "integrity") {
      const f = e.payload as unknown as IntegrityFlag;
      marks.push({ t: sec(e.t), kind: "integrity", title: "Noted", detail: f.detail });
    } else if (e.kind === "chaos_run") {
      const c = e.payload as unknown as ChaosRun;
      marks.push({ t: sec(e.t), kind: c.verdict === "held" ? "good" : "issue", title: `${c.kind === "verify" ? "Verify" : "Attack"}: ${c.verdict}`, detail: c.summary });
    }
  }
  return marks.sort((a, b) => a.t - b.t);
}

export function LiveReport({ id }: { id: string }) {
  const [view, setView] = useState<View>({ kind: "loading" });

  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      try {
        const res = await api.report(id);
        if (!live) return;
        if (res.status === "generating") {
          setView({ kind: "generating" });
          timer = setTimeout(load, POLL_MS);
          return;
        }
        const report = res.report;
        const [timeline, title] = await Promise.all([
          api.timeline(id).catch(() => [] as TimelineEvent[]),
          report.coding
            ? api.problem(report.coding.problem_slug).then((p) => p.title).catch(() => "Coding interview")
            : api.session(id).then((s) => s.project_id ?? "Project defense").catch(() => "Project defense"),
        ]);
        if (!live) return;
        setView({ kind: "ready", report, timeline, title, file: mainFile(timeline, "solution.py") });
      } catch (err) {
        if (!live) return;
        const stillLive = err instanceof ApiError && err.code === "session_live";
        const mode = stillLive ? (await api.session(id).catch(() => null))?.config.mode : undefined;
        if (live) setView({ kind: "error", message: errorText(err), back: mode ? `/${mode}/${id}` : undefined });
      }
    };
    void load();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [id]);

  if (view.kind !== "ready") {
    return (
      <div className="rp live-wait">
        <header className="rm-top">
          <Link href="/" className="rm-brand" translate="no">
            Ares
          </Link>
          <span className="rp-crumb">Report</span>
        </header>
        <div className="live-wait-body" role="status">
          {view.kind === "loading" && <p>Loading the report…</p>}
          {view.kind === "generating" && (
            <>
              <h1>Writing your report</h1>
              <p>Ares is scoring the session and picking out its key moments. This page updates by itself.</p>
            </>
          )}
          {view.kind === "error" && (
            <>
              <h1>{view.back ? "This interview is still going" : "No report"}</h1>
              <p>{view.message}</p>
              {view.back && (
                <p>
                  <Link href={view.back} className="ui-btn ui-btn-primary">
                    Back to the Interview
                  </Link>
                </p>
              )}
            </>
          )}
        </div>
      </div>
    );
  }

  const { report, timeline, title, file } = view;
  const defense = report.defense;
  return (
    <ReportView
      title={title}
      crumb={`Report · ${title}`}
      report={report}
      replay={timeline}
      file={file}
      transcript={linesOf(timeline)}
      marks={marksOf(report, timeline)}
      activity={timeline.filter((e) => (e.kind as string) === MODEL_ACTIVITY_KIND).map((e) => e.payload as unknown as ModelActivity)}
    >
      {defense && <DefenseExtras defense={defense} />}
    </ReportView>
  );
}
