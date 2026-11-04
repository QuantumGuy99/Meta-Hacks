"use client";

import { useState } from "react";
import type { AssistantEdit, AssistantTurn, ClientMessage } from "@/types/contracts";

// The fix assistant (DEF-11, PLAN §11.9): a Muse Spark coding assistant beside the fix stage. It sees the
// finding, the attack and the editor's files, answers, and may propose edits the candidate applies or not.
// Every ask, reply and apply is on the timeline, so the report shows how much of the fix the AI wrote.

const MAX_ASK = 4000; // the backend's MAX_CHAT_CHARS

function changedLines(before: string, after: string): number {
  const a = before.split("\n");
  const b = after.split("\n");
  let same = 0;
  while (same < a.length && same < b.length && a[same] === b[same]) same += 1;
  let end = 0;
  while (end < a.length - same && end < b.length - same && a[a.length - 1 - end] === b[b.length - 1 - end]) end += 1;
  return Math.max(a.length, b.length) - same - end;
}

export function FixAssistant({
  turns,
  files,
  original,
  enabled,
  send,
  onApply,
}: {
  turns: AssistantTurn[];
  /** the editor's files as they are now */
  files: Record<string, string> | null;
  /** the project as it was, so only edited files go with a question */
  original: Record<string, string>;
  /** fix or verify: the assistant opens once the grill is done */
  enabled: boolean;
  send: (msg: ClientMessage) => void;
  onApply: (edits: AssistantEdit[]) => void;
}) {
  const [text, setText] = useState("");
  const applied = new Set(turns.filter((t) => t.kind === "apply").flatMap((t) => t.accepted.map((p) => `${t.reply_to}:${p}`)));
  const thread = turns.filter((t) => t.kind !== "apply");
  const last = thread[thread.length - 1];
  const thinking = last?.kind === "ask";

  const ask = () => {
    const question = text.trim();
    if (!question || !files || thinking) return;
    const edited = Object.fromEntries(Object.entries(files).filter(([p, code]) => original[p] !== code));
    send({ type: "assistant.ask", text: question.slice(0, MAX_ASK), files: edited });
    setText("");
  };

  const apply = (reply: AssistantTurn, edits: AssistantEdit[]) => {
    onApply(edits);
    send({ type: "assistant.apply", reply_id: reply.id, accepted: edits.map((e) => e.path) });
  };

  return (
    <section className="df-assist" aria-labelledby="df-assist-title">
      <header>
        <h3 id="df-assist-title">Fix assistant</h3>
        <span className="df-muted">Muse Spark · recorded in your report</span>
      </header>
      {!enabled ? (
        <p className="df-muted">The assistant opens once you&apos;ve answered the grill.</p>
      ) : (
        <>
          <ol className="df-assist-thread" aria-live="polite">
            {thread.length === 0 && (
              <li className="df-muted">Ask for help with the fix: where to start, what a change would look like, or why Verify still broke.</li>
            )}
            {thread.map((t) =>
              t.kind === "ask" ? (
                <li key={t.id} className="is-you">
                  <span className="df-muted">You</span>
                  <p>{t.text}</p>
                </li>
              ) : (
                <li key={t.id} className="is-ai">
                  <span className="df-muted">Assistant</span>
                  <p>{t.text}</p>
                  {t.edits.length > 0 && (
                    <ul className="df-assist-edits">
                      {t.edits.map((e) => {
                        const done = applied.has(`${t.id}:${e.path}`);
                        return (
                          <li key={e.path}>
                            <code translate="no">{e.path}</code>
                            <span className="df-muted">{changedLines(files?.[e.path] ?? original[e.path] ?? "", e.content)} lines change</span>
                            <button type="button" className="ui-btn" disabled={done} onClick={() => apply(t, [e])}>
                              {done ? "Applied" : "Apply"}
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </li>
              ),
            )}
            {thinking && <li className="df-muted">Thinking…</li>}
          </ol>
          <form
            className="df-assist-ask"
            onSubmit={(e) => {
              e.preventDefault();
              ask();
            }}
          >
            <textarea
              rows={3}
              maxLength={MAX_ASK}
              value={text}
              placeholder="Ask the assistant…"
              aria-label="Ask the fix assistant"
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  ask();
                }
              }}
            />
            <button type="submit" className="ui-btn" disabled={!text.trim() || thinking || !files}>
              {thinking ? "Thinking…" : "Ask"}
            </button>
          </form>
        </>
      )}
    </section>
  );
}
