"use client";

import { clock } from "@/lib/fixtures";
import type { LiveState } from "@/lib/session";
import type { IntegrityFlag, StepStatus, SuspectedIssue } from "@/types/contracts";

// The interviewer's notes (PLAN §14.2): the candidate's stated plan, the rubric steps with their live
// statuses and the issues the analyzer suspects, from the latest notes.update. Off by default; the Notes
// button in the top bar opens it. Integrity notes are facts, never accusations (PLAN §4.4 rule 6).

const STEP: Record<StepStatus, [label: string, className: string]> = {
  not_started: ["Not yet", "st-prog"],
  in_progress: ["Working", "st-prog"],
  done: ["Done", "st-done"],
  incorrect: ["Check", "st-miss"],
  skipped: ["Skipped", "st-prog"],
};

const ISSUE: Record<SuspectedIssue["kind"], string> = {
  bug: "Possible bug",
  edge_case: "Edge case",
  complexity: "Complexity",
  style: "Style",
};

export function NotesPanel({ notes, flags }: { notes: LiveState["notes"]; flags: IntegrityFlag[] }) {
  const empty = !notes && flags.length === 0;
  return (
    <section className="rm-notes-panel" aria-label="Interviewer's notes">
      <h2>Interviewer&apos;s notes</h2>
      {empty && <p className="rm-notes-empty">Notes appear after the interviewer&apos;s first look at your code.</p>}
      {notes && (
        <>
          <div className="rm-notes-block">
            <h3>Your plan</h3>
            <p className={notes.stated_plan ? undefined : "rm-notes-empty"}>
              {notes.stated_plan ?? "Not stated yet. Say or type your approach before you code."}
            </p>
          </div>
          {notes.steps.length > 0 && (
            <div className="rm-notes-block">
              <h3>Steps</h3>
              <ol>
                {notes.steps.map((s, i) => {
                  const [label, cls] = STEP[s.status];
                  return (
                    <li key={s.step_id} className="note">
                      <span className={`st ${cls}`}>{label}</span>
                      <span>
                        Step {i + 1}
                        {s.evidence ? `: ${s.evidence}` : ""}
                      </span>
                    </li>
                  );
                })}
              </ol>
            </div>
          )}
          {notes.issues.length > 0 && (
            <div className="rm-notes-block">
              <h3>Worth a look</h3>
              <ul>
                {notes.issues.map((issue, i) => (
                  <li key={`${issue.kind}-${issue.line}-${i}`} className="note">
                    <span className="st st-prog">{ISSUE[issue.kind]}</span>
                    <span>
                      {issue.line ? `Line ${issue.line}: ` : ""}
                      {issue.description}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
      {flags.length > 0 && (
        <div className="rm-notes-block">
          <h3>Noted</h3>
          <ul>
            {flags.map((f) => (
              <li key={f.id} className="note">
                <span className="st st-prog">{clock(f.t / 1000)}</span>
                <span>{f.detail.charAt(0).toUpperCase() + f.detail.slice(1)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
