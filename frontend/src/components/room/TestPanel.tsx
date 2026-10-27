"use client";

import NumberFlow from "@number-flow/react";
import type { RunResult } from "@/types/contracts";

// Test results under the editor, shaped like the run.result message. Hidden tests never show
// their inputs: only a count, and an error name for the ones that failed.
export function TestPanel({ result, running }: { result: RunResult | null; running: boolean }) {
  const visible = result?.cases.filter((c) => c.visible) ?? [];
  const hiddenFailed = result?.cases.filter((c) => !c.visible && !c.passed) ?? [];
  const runtime = result?.cases.reduce((ms, c) => ms + c.runtime_ms, 0) ?? 0;

  return (
    <section className="rm-tests" aria-label="Test results" aria-busy={running}>
      <header className="rm-panel-head">
        <span>{result?.kind === "submit" ? "Submission" : "Tests"}</span>
        {result && (
          <span className={result.passed === result.total ? "rm-pass" : "rm-fail"} aria-live="polite">
            <NumberFlow value={result.passed} /> of {result.total} passed · {runtime} ms
          </span>
        )}
        {running && <span className="rm-running">Running…</span>}
      </header>
      {!result && !running && <p className="rm-empty">Run the visible tests with Run or Ctrl+Enter.</p>}
      {result && (
        <ul className="rm-cases">
          {visible.map((c) => (
            <li key={c.id} className={c.passed ? "is-pass" : "is-fail"}>
              <span className="rm-case-status">{c.passed ? "Pass" : "Fail"}</span>
              <code translate="no">{c.input_repr}</code>
              <span className="rm-case-io">
                expected <code translate="no">{c.expected_repr}</code>
                {!c.passed && (
                  <>
                    , got <code translate="no">{c.actual_repr}</code>
                  </>
                )}
              </span>
            </li>
          ))}
          {result.kind === "submit" && (
            <li className={hiddenFailed.length ? "is-fail" : "is-pass"}>
              <span className="rm-case-status">{hiddenFailed.length ? "Fail" : "Pass"}</span>
              <span>
                Hidden tests: {result.total - visible.length - hiddenFailed.length} of {result.total - visible.length} passed
                {hiddenFailed.length > 0 && ` · ${hiddenFailed.map((c) => c.error ?? "failed").join(", ")}`}
              </span>
            </li>
          )}
        </ul>
      )}
    </section>
  );
}
