"use client";

import {
  analysis,
  CLARIFY_QUESTION,
  codingReport,
  DRAFT_CODE,
  FIXED_CODE,
  nudge,
  problem,
  tabFlag,
  transcript,
  visibleRun,
  WRAP_UP_QUESTION,
} from "@/lib/fixtures";
import type { EditorEvent, TimelineEvent } from "@/types/contracts";
import { ReportView, type ReportLine, type ReportMark } from "./ReportView";

// Report + replay demo for the shared Quiet Streak session: scores, moments and metrics come from the report
// fixture, and a scripted timeline of editor events feeds the replay. The live report renders the same view.

const report = codingReport;
const metrics = report.metrics;
const sec = (ms: number) => Math.round(ms / 1000);

// Report moments, plus the timeline's run and integrity events as extra markers.
const MARKS: ReportMark[] = [
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

const LINES: ReportLine[] = [
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

export function ReportDemo() {
  return (
    <ReportView
      title={problem.title}
      crumb={`Report · ${problem.title} · Demo`}
      report={report}
      replay={REPLAY}
      file={FILE}
      transcript={TRANSCRIPT}
      marks={MARKS}
    />
  );
}
