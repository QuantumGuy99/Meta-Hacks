"use client";

import { AnimatePresence, m } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Streamdown } from "streamdown";
import "streamdown/styles.css";
import { levelLabel } from "@/lib/fixtures";
import type { InterventionLevel, StepStatus } from "@/types/contracts";

export type RoomMessage = {
  id: string;
  who: "interviewer" | "you";
  level?: InterventionLevel;
  text: string;
};

/** A line in the interviewer's notes: a rubric step's progress, or a neutral integrity note. */
export type RoomNote = { title: string; status: StepStatus | "noted"; evidence?: string };

const NOTE_CHIP: Record<RoomNote["status"], [label: string, className: string]> = {
  done: ["Done", "st-done"],
  in_progress: ["Watching", "st-prog"],
  not_started: ["Missing", "st-miss"],
  incorrect: ["Missing", "st-miss"],
  skipped: ["Skipped", "st-prog"],
  noted: ["Noted", "st-prog"],
};

export type InterviewerState = "idle" | "listening" | "thinking" | "speaking";

const CHARS_PER_TICK = 3;

// Reveals the newest interviewer message a few characters at a time, the way a streamed
// reply arrives; Streamdown renders the partial markdown safely while it's incomplete.
const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function StreamedText({ text, live, onDone }: { text: string; live: boolean; onDone?: () => void }) {
  // Reduced motion: show the whole message at once instead of streaming it.
  const [shown, setShown] = useState(() => (live && !prefersReducedMotion() ? 0 : text.length));
  const done = useRef(onDone);
  useEffect(() => {
    done.current = onDone;
  });
  // Fire onDone once per message, even when effects re-run in development.
  const fired = useRef(false);

  useEffect(() => {
    if (!live) return;
    const finish = () => {
      if (fired.current) return;
      fired.current = true;
      done.current?.();
    };
    if (prefersReducedMotion()) {
      finish();
      return;
    }
    let n = 0;
    const id = window.setInterval(() => {
      n = Math.min(text.length, n + CHARS_PER_TICK);
      setShown(n);
      if (n >= text.length) {
        window.clearInterval(id);
        finish();
      }
    }, 24);
    return () => window.clearInterval(id);
  }, [text, live]);

  const animating = live && shown < text.length;
  return (
    <Streamdown className="rm-md" mode={animating ? "streaming" : "static"} isAnimating={animating} caret="block" controls={false}>
      {text.slice(0, shown)}
    </Streamdown>
  );
}

export function InterviewerPanel({
  messages,
  state,
  streamingId,
  onStreamDone,
  onAsk,
  onHint,
  hintsLeft = 0,
  notes = [],
  caption = null,
  extra = null,
}: {
  messages: RoomMessage[];
  state: InterviewerState;
  streamingId: string | null;
  onStreamDone: () => void;
  onAsk: (text: string) => void;
  /** Leave out to hide the Hint button (defense has no hints in chat). */
  onHint?: () => void;
  hintsLeft?: number;
  notes?: RoomNote[];
  /** A live caption under the messages: what the candidate is saying right now (partial transcript). */
  caption?: string | null;
  /** Extra controls in the ask row, e.g. the mic toggle. */
  extra?: ReactNode;
}) {
  const [draft, setDraft] = useState("");
  const list = useRef<HTMLDivElement>(null);

  // Keep the newest message in view.
  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, streamingId]);

  return (
    <section className="rm-panel rm-interviewer" aria-label="Interviewer">
      <header className="rm-panel-head">
        <span className={`rm-state rm-state-${state}`} aria-hidden />
        <span>
          Interviewer · <span aria-live="polite">{state}</span>
        </span>
      </header>

      <div className="rm-msgs" ref={list} aria-live="polite">
        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <m.div
              key={msg.id}
              className={`msg ${msg.who === "you" ? "msg-you" : "msg-ai"} ${msg.level === "nudge" ? "msg-nudge" : ""}`}
              layout="position"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              <span className="msg-who">
                {msg.who === "you" ? "You" : "Interviewer"}
                {msg.level ? ` · ${levelLabel(msg.level)}` : ""}
              </span>
              {msg.who === "you" ? (
                <p>{msg.text}</p>
              ) : (
                <StreamedText text={msg.text} live={msg.id === streamingId} onDone={onStreamDone} />
              )}
            </m.div>
          ))}
        </AnimatePresence>
        {caption && (
          <p className="msg-caption" aria-live="off">
            <span className="msg-who">You · speaking</span>
            {caption}
          </p>
        )}
      </div>

      {notes.length > 0 && (
        <div className="room-notes rm-notes" aria-label="Interviewer's notes" aria-live="polite">
          {notes.map((n) => {
            const [label, cls] = NOTE_CHIP[n.status];
            return (
              <div key={n.title} className="note" title={n.evidence}>
                <span className={`st ${cls}`}>{label}</span>
                {n.title}
              </div>
            );
          })}
        </div>
      )}

      <form
        className="rm-ask"
        onSubmit={(e) => {
          e.preventDefault();
          const text = draft.trim();
          if (!text) return;
          onAsk(text);
          setDraft("");
        }}
      >
        <label className="sr-only" htmlFor="rm-ask-input">
          Ask the interviewer
        </label>
        <input
          id="rm-ask-input"
          name="ask"
          autoComplete="off"
          placeholder="Ask a question or explain your plan…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button type="submit" className="ui-btn ui-btn-primary" disabled={!draft.trim()}>
          Ask
        </button>
        {onHint && (
          <button type="button" className="ui-btn" onClick={onHint} disabled={hintsLeft === 0}>
            Hint
          </button>
        )}
        {extra}
      </form>
    </section>
  );
}
