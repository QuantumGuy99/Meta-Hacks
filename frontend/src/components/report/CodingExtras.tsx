"use client";

import type { CodingExtra, StepStatus } from "@/types/contracts";

// The coding part of the report (PLAN §14.5): the approach the candidate took, whether the wrap-up
// complexity answer was right (#45), and where each rubric step ended up.

const STEP: Record<StepStatus, [label: string, className: string]> = {
  done: ["Done", "is-ok"],
  in_progress: ["Partly", "is-mid"],
  not_started: ["Not done", "is-bad"],
  incorrect: ["Off track", "is-bad"],
  skipped: ["Skipped", "is-mid"],
};

export function CodingExtras({ coding }: { coding: CodingExtra }) {
  // null: not graded (never asked, no answer, no model, or the grading failed), so say no more than that
  const complexity =
    coding.complexity_answer_ok === null
      ? { text: "Not graded", cls: "is-mid" }
      : coding.complexity_answer_ok
        ? { text: "Right", cls: "is-ok" }
        : { text: "Not quite", cls: "is-bad" };
  return (
    <section className="rp-coding" aria-labelledby="rp-coding-title">
      <h2 id="rp-coding-title">How you solved it</h2>
      <dl className="rp-coding-facts">
        <div>
          <dt>Approach</dt>
          <dd>{coding.approach ?? "No approach was recorded."}</dd>
        </div>
        <div>
          <dt>Complexity answer</dt>
          <dd>
            <span className={`rp-chip ${complexity.cls}`}>{complexity.text}</span>
          </dd>
        </div>
      </dl>
      {coding.steps.length > 0 && (
        <ol className="rp-steps">
          {coding.steps.map((s, i) => {
            const [label, cls] = STEP[s.status];
            return (
              <li key={s.step_id}>
                <span className={`rp-chip ${cls}`}>{label}</span>
                <span>
                  Step {i + 1}
                  {s.evidence ? `: ${s.evidence}` : ""}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
