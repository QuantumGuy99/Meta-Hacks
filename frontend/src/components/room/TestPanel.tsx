"use client";

import NumberFlow from "@number-flow/react";

export type CaseResult = {
  id: string;
  passed: boolean;
  input: string;
  expected: string;
  actual: string;
};

export type RunResult = { kind: "run" | "submit"; cases: CaseResult[]; runtimeMs: number };

// Visible test results under the editor; hidden-test inputs are never shown (counts only).
export function TestPanel({ result, running }: { result: RunResult | null; running: boolean }) {
  const passed = result?.cases.filter((c) => c.passed).length ?? 0;
  const total = result?.cases.length ?? 0;

  return (
    <section className="rm-tests" aria-label="Test results" aria-busy={running}>
      <header className="rm-panel-head">
        <span>Tests</span>
        {result && (
          <span className={passed === total ? "rm-pass" : "rm-fail"} aria-live="polite">
            <NumberFlow value={passed} /> of {total} passed · {result.runtimeMs} ms
          </span>
        )}
        {running && <span className="rm-running">Running…</span>}
      </header>
      {!result && !running && <p className="rm-empty">Run the visible tests with Run or Ctrl+Enter.</p>}
      {result && (
        <ul className="rm-cases">
          {result.cases.map((c) => (
            <li key={c.id} className={c.passed ? "is-pass" : "is-fail"}>
              <span className="rm-case-status">{c.passed ? "Pass" : "Fail"}</span>
              <code translate="no">{c.input}</code>
              <span className="rm-case-io">
                expected <code translate="no">{c.expected}</code>
                {!c.passed && (
                  <>
                    , got <code translate="no">{c.actual}</code>
                  </>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
