"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, errorText } from "@/lib/api";
import type { GuideAction, GuideAsk, GuideTurn } from "@/types/guide.draft";
import "./guide.css";

// "Ask Ares" (#25, PR #51): a small guide on every page that answers questions about using the app and can
// suggest one allowlisted step. Code decides what a suggestion does: it only ever opens a page (at most a
// prefilled setup page), never starts a session by itself. It's off in a live interview room, where it
// would be a channel for help with the problem.

const LIVE_ROOM = /^\/(coding|defense)\/(?!demo$)[^/]+$/;
const MAX_QUESTION = 500;
const HISTORY = 6;
const STARTERS = ["What's Project Defense?", "How does the interviewer score me?", "Start an easy coding interview"];

type Turn = GuideTurn & { action?: GuideAction };

function pageOf(path: string): GuideAsk["page"] {
  if (path === "/") return "home";
  if (path === "/coding") return "coding_setup";
  if (path === "/defense") return "defense_picker";
  if (LIVE_ROOM.test(path)) return "room";
  if (path.startsWith("/report/")) return "report";
  return "other";
}

/** Where a suggestion leads, and what its button says; null for none. */
function suggestion(a: GuideAction | undefined): { href: string; label: string } | null {
  if (!a) return null;
  switch (a.kind) {
    case "open_page":
      if (a.page === "home") return { href: "/", label: "Go to the home page" };
      if (a.page === "coding") return { href: "/coding", label: "Open coding interview setup" };
      if (a.page === "defense") return { href: "/defense", label: "Open Project Defense" };
      if (a.page === "report") return { href: "/report/demo", label: "See a sample report" };
      return null;
    case "start_coding":
      return {
        href: a.difficulty ? `/coding?difficulty=${a.difficulty}` : "/coding",
        label: a.difficulty ? `Set up a ${a.difficulty} coding interview` : "Set up a coding interview",
      };
    case "start_defense":
      return {
        href: a.project_id ? `/defense?project=${encodeURIComponent(a.project_id)}` : "/defense",
        label: a.project_id ? `Set up a defense of ${a.project_id}` : "Pick a project to defend",
      };
    default:
      return null;
  }
}

export function AskAres() {
  const path = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLOListElement>(null);

  useEffect(() => {
    if (open) input.current?.focus({ preventScroll: true });
  }, [open]);
  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: "smooth" });
  }, [turns.length, busy]);

  if (LIVE_ROOM.test(path)) return null; // off during a live interview (#25)

  const ask = async (question: string) => {
    const text = question.trim().slice(0, MAX_QUESTION);
    if (!text || busy) return;
    const history = turns.slice(-HISTORY).map(({ role, text: t }) => ({ role, text: t }));
    setTurns((all) => [...all, { role: "user", text }]);
    setDraft("");
    setError(null);
    setBusy(true);
    try {
      const reply = await api.guide({ question: text, page: pageOf(path), in_session: false, history });
      setTurns((all) => [...all, { role: "guide", text: reply.reply, action: reply.action }]);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const follow = (href: string) => {
    router.push(href);
    setOpen(false);
  };

  return (
    <div className="ask" data-ui>
      {open && (
        <section
          className="ask-panel"
          role="dialog"
          aria-label="Ask Ares"
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
          }}
        >
          <header className="ask-head">
            <strong>Ask Ares</strong>
            <span>How the app works and where to start</span>
            <button type="button" className="ask-close" onClick={() => setOpen(false)} aria-label="Close the guide">
              ×
            </button>
          </header>
          <ol className="ask-list" ref={list} aria-live="polite">
            {turns.length === 0 && (
              <li className="ask-empty">
                <p>Ask about either interview, what gets scored, or where to begin.</p>
                <div className="ask-starters">
                  {STARTERS.map((q) => (
                    <button key={q} type="button" onClick={() => void ask(q)}>
                      {q}
                    </button>
                  ))}
                </div>
              </li>
            )}
            {turns.map((t, i) => {
              const next = t.role === "guide" ? suggestion(t.action) : null;
              return (
                <li key={i} className={t.role === "user" ? "ask-turn is-you" : "ask-turn"}>
                  <p>{t.text}</p>
                  {next && (
                    <button type="button" className="ask-action" onClick={() => follow(next.href)}>
                      {next.label}
                    </button>
                  )}
                </li>
              );
            })}
            {busy && <li className="ask-turn is-busy">Thinking…</li>}
          </ol>
          {error && (
            <p className="ask-error" role="alert">
              {error}
            </p>
          )}
          <form
            className="ask-form"
            onSubmit={(e) => {
              e.preventDefault();
              void ask(draft);
            }}
          >
            <label htmlFor="ask-input" className="sr-only">
              Your question
            </label>
            <input
              id="ask-input"
              ref={input}
              autoComplete="off"
              maxLength={MAX_QUESTION}
              placeholder="Ask about using Ares…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
            <button type="submit" disabled={!draft.trim() || busy}>
              Ask
            </button>
          </form>
        </section>
      )}
      <button type="button" className="ask-toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        {open ? "Close" : "Ask Ares"}
      </button>
    </div>
  );
}
