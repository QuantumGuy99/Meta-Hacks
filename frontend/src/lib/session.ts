"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import type {
  AuditPublic,
  ChaosMetric,
  ChaosRun,
  ClientMessage,
  ErrorMsg,
  Finding,
  GrillTurn,
  IntegrityFlag,
  Intervention,
  Phase,
  RunResult,
  SamHighlight,
  ServerMessage,
  Session,
  StepProgress,
  SuspectedIssue,
  TimelineEvent,
  TranscriptTurn,
  Verdict,
} from "@/types/contracts";
import { api } from "./api";
import { connectSession, type SessionSocket, type SocketStatus } from "./ws";

// One live session's state, fed only by ServerMessages (PLAN §6 `store.ts`). A reducer, not a global store:
// each room owns exactly one session, so there's nothing to share across the tree.

export type InterviewerState = "idle" | "listening" | "thinking" | "speaking";

export type LiveState = {
  status: SocketStatus;
  session: Session | null;
  phase: Phase | null;
  remainingS: number | null;
  /** performance.now() when remainingS arrived, so the timer can count down between updates. */
  syncedAt: number;
  interviewer: InterviewerState;
  interventions: Intervention[];
  /** The feed shows one new interviewer message at a time: the one streaming in, then the queue. */
  streamingId: string | null;
  pending: string[];
  shown: string[];
  turns: TranscriptTurn[];
  runs: RunResult[];
  notes: { steps: StepProgress[]; issues: SuspectedIssue[]; stated_plan: string | null } | null;
  flags: IntegrityFlag[];
  audit: AuditPublic | null;
  metrics: ChaosMetric[];
  chaosRuns: ChaosRun[];
  grill: { turn: GrillTurn; finding: Finding }[];
  highlight: SamHighlight | null;
  verdict: Verdict | null;
  reportReady: boolean;
  error: (ErrorMsg & { at: number }) | null;
};

export const initialLive: LiveState = {
  status: "connecting",
  session: null,
  phase: null,
  remainingS: null,
  syncedAt: 0,
  interviewer: "idle",
  interventions: [],
  streamingId: null,
  pending: [],
  shown: [],
  turns: [],
  runs: [],
  notes: null,
  flags: [],
  audit: null,
  metrics: [],
  chaosRuns: [],
  grill: [],
  highlight: null,
  verdict: null,
  reportReady: false,
  error: null,
};

type Action =
  | { type: "status"; status: SocketStatus }
  | { type: "msg"; msg: ServerMessage; at: number; wall: number }
  | { type: "history"; events: TimelineEvent[] }
  | { type: "streamDone" };

/** What a reload missed: the socket only resends session.state, so the rest comes from the public timeline. */
function addHistory(state: LiveState, events: TimelineEvent[]): LiveState {
  let next = state;
  for (const e of events) {
    const p = e.payload as never;
    switch (e.kind) {
      case "intervention": {
        const iv = p as Intervention;
        if (iv.suppressed || next.interventions.some((x) => x.id === iv.id)) break;
        next = { ...next, interventions: [...next.interventions, iv], shown: [...next.shown, iv.id] };
        break;
      }
      case "transcript":
        next = { ...next, turns: upsert(next.turns, p as TranscriptTurn, (x) => x.turn_id) };
        break;
      case "run":
        next = { ...next, runs: upsert(next.runs, p as RunResult, (x) => x.run_id) };
        break;
      case "integrity":
        next = { ...next, flags: upsert(next.flags, p as IntegrityFlag, (x) => x.id) };
        break;
      case "chaos_run":
        next = { ...next, chaosRuns: upsert(next.chaosRuns, p as ChaosRun, (x) => x.id) };
        break;
      case "verdict":
        next = { ...next, verdict: p as Verdict };
        break;
    }
  }
  return next;
}

/** Messages older than this when they arrive are history (a reload or reconnect) and appear without streaming. */
const HISTORY_MS = 8000;

function addIntervention(state: LiveState, iv: Intervention, wall: number): LiveState {
  if (iv.suppressed) return state;
  const known = state.interventions.some((x) => x.id === iv.id);
  const interventions = upsert(state.interventions, iv, (x) => x.id);
  if (known) return { ...state, interventions };
  const started = state.session?.started_at ? Date.parse(state.session.started_at) : Number.NaN;
  if (Number.isFinite(started) && iv.t < wall - started - HISTORY_MS) {
    return { ...state, interventions, shown: [...state.shown, iv.id] };
  }
  if (state.streamingId === null) {
    return { ...state, interventions, shown: [...state.shown, iv.id], streamingId: iv.id };
  }
  return { ...state, interventions, pending: [...state.pending, iv.id] };
}

/** Replace the item with the same key, or append it. Reconnects can resend what we already have. */
function upsert<T>(list: T[], item: T, key: (x: T) => string): T[] {
  const k = key(item);
  const i = list.findIndex((x) => key(x) === k);
  if (i === -1) return [...list, item];
  const next = list.slice();
  next[i] = item;
  return next;
}

export function reduceLive(state: LiveState, action: Action): LiveState {
  if (action.type === "status") return { ...state, status: action.status };
  if (action.type === "history") return addHistory(state, action.events);
  if (action.type === "streamDone") {
    const [next, ...rest] = state.pending;
    return { ...state, streamingId: next ?? null, pending: rest, shown: next ? [...state.shown, next] : state.shown };
  }
  const msg = action.msg;
  switch (msg.type) {
    case "session.state":
      return {
        ...state,
        session: msg.session,
        phase: msg.phase,
        remainingS: msg.remaining_s,
        syncedAt: action.at,
        interviewer: msg.interviewer_state,
      };
    case "interviewer.message":
      return addIntervention(state, msg.intervention, action.wall);
    case "transcript.update":
      return { ...state, turns: upsert(state.turns, msg.turn, (x) => x.turn_id) };
    case "run.result":
      return { ...state, runs: upsert(state.runs, msg.result, (x) => x.run_id) };
    case "notes.update":
      return { ...state, notes: { steps: msg.steps, issues: msg.issues, stated_plan: msg.stated_plan } };
    case "integrity.flag":
      return { ...state, flags: upsert(state.flags, msg.flag, (x) => x.id) };
    case "defense.audit":
      return { ...state, audit: msg.audit };
    case "defense.chaos.metric":
      return { ...state, metrics: upsert(state.metrics, msg.metric, (x) => `${x.run_id}:${x.t_ms}`) };
    case "defense.chaos.done":
      return { ...state, chaosRuns: upsert(state.chaosRuns, msg.run, (x) => x.id) };
    case "defense.grill.eval":
      return { ...state, grill: upsert(state.grill, { turn: msg.turn, finding: msg.finding }, (x) => x.turn.finding_id) };
    case "defense.sam.highlight":
      return { ...state, highlight: msg.highlight };
    case "defense.verdict":
      return { ...state, verdict: msg.verdict };
    case "report.ready":
      return { ...state, reportReady: true };
    case "error":
      return { ...state, error: { ...msg, at: action.at } };
    default:
      return state;
  }
}

/** Connects to the session socket for as long as the component is mounted. */
export function useLiveSession(id: string) {
  const [state, dispatch] = useReducer(reduceLive, initialLive);
  const socket = useRef<SessionSocket | null>(null);

  useEffect(() => {
    const s = connectSession(id, {
      onMessage: (msg) => dispatch({ type: "msg", msg, at: performance.now(), wall: Date.now() }),
      onStatus: (status) => dispatch({ type: "status", status }),
    });
    socket.current = s;
    let live = true;
    api
      .timeline(id)
      .then((events) => live && dispatch({ type: "history", events }))
      .catch(() => {}); // a brand-new session has no history; a missing one shows as not_found on the socket
    return () => {
      live = false;
      socket.current = null;
      s.close();
    };
  }, [id]);

  const send = useCallback((msg: ClientMessage) => socket.current?.send(msg), []);
  const streamDone = useCallback(() => dispatch({ type: "streamDone" }), []);
  return { state, send, streamDone };
}

export type FeedMessage = { id: string; who: "interviewer" | "you"; level?: Intervention["level"]; text: string };

/** The interviewer's shown messages and the candidate's finished turns, in session order. */
export function feedMessages(state: LiveState): FeedMessage[] {
  const shown = new Set(state.shown);
  const items: (FeedMessage & { t: number })[] = [
    ...state.interventions
      .filter((iv) => shown.has(iv.id))
      .map((iv) => ({ id: iv.id, who: "interviewer" as const, level: iv.level, text: iv.text, t: iv.t })),
    // the interviewer's own turns duplicate its interventions, so only the candidate's are listed
    ...state.turns
      .filter((turn) => turn.speaker === "candidate" && turn.final && turn.text.trim())
      .map((turn) => ({ id: turn.turn_id, who: "you" as const, text: turn.text, t: turn.start_ms })),
  ];
  return items.sort((a, b) => a.t - b.t);
}

/** What the candidate is saying right now (the latest partial voice turn), if anything. */
export function liveCaption(state: LiveState): string | null {
  for (let i = state.turns.length - 1; i >= 0; i--) {
    const turn = state.turns[i];
    if (turn.speaker === "candidate") return turn.final ? null : turn.text || null;
  }
  return null;
}

/** Seconds left, counting down locally between the server's session.state updates. */
export function useRemaining(state: LiveState): number | null {
  const [now, setNow] = useState(0);
  const live = state.remainingS !== null && state.phase !== "ended";
  useEffect(() => {
    if (!live) return;
    const tick = () => setNow(performance.now());
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [live, state.syncedAt]);
  if (state.remainingS === null) return null;
  if (!live || now < state.syncedAt) return Math.max(0, Math.round(state.remainingS));
  return Math.max(0, Math.round(state.remainingS - (now - state.syncedAt) / 1000));
}

/** Socket status as one short line, or null while everything is fine. */
export function statusLine(status: SocketStatus): string | null {
  switch (status) {
    case "connecting":
      return "Connecting…";
    case "reconnecting":
      return "Connection lost. Reconnecting…";
    case "not_found":
      return "This session doesn't exist on the server.";
    default:
      return null;
  }
}
