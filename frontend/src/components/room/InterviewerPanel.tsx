"use client";

import { AnimatePresence, m } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { Streamdown } from "streamdown";
import "streamdown/styles.css";

export type RoomMessage = {
  id: string;
  who: "interviewer" | "you";
  level?: "Info" | "Nudge" | "Question" | "Hint" | "Concept";
  text: string;
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
  hintsLeft,
}: {
  messages: RoomMessage[];
  state: InterviewerState;
  streamingId: string | null;
  onStreamDone: () => void;
  onAsk: (text: string) => void;
  onHint: () => void;
  hintsLeft: number;
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
              className={`msg ${msg.who === "you" ? "msg-you" : "msg-ai"} ${msg.level === "Nudge" ? "msg-nudge" : ""}`}
              layout="position"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              <span className="msg-who">
                {msg.who === "you" ? "You" : "Interviewer"}
                {msg.level ? ` · ${msg.level}` : ""}
              </span>
              {msg.who === "you" ? (
                <p>{msg.text}</p>
              ) : (
                <StreamedText text={msg.text} live={msg.id === streamingId} onDone={onStreamDone} />
              )}
            </m.div>
          ))}
        </AnimatePresence>
      </div>

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
        <button type="button" className="ui-btn" onClick={onHint} disabled={hintsLeft === 0}>
          Hint
        </button>
      </form>
    </section>
  );
}
