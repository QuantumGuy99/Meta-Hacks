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
import {
  MODEL_ACTIVITY_KIND,
  type ActivityEvent,
  type ModelActivity,
  type ModelActivityMsg,
} from "@/types/model-activity.draft";
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
  /** Date.now() when something reached this browser over the socket: an intervention by its id, a run as
   * `run:<id>`, an attack as `chaos:<id>`. Nothing loaded from the timeline is in here, so a reload doesn't
   * replay toasts or timers for things that happened before it. */
  arrived: Record<string, number>;
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
  /** model.activity events for the Under the hood strip (PR #39), oldest first. */
  activity: ActivityEvent[];
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
  arrived: {},
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
  activity: [],
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
      case MODEL_ACTIVITY_KIND as TimelineEvent["kind"]:
        next = { ...next, activity: addActivity(next.activity, p as ModelActivity) };
        break;
      case "chaos_metric":
        next = { ...next, metrics: upsert(next.metrics, p as ChaosMetric, (x) => `${x.run_id}:${x.t_ms}`) };
        break;
      case "audit":
        // public while the session is live (no explanations); the socket doesn't resend it after a reload
        if (!next.audit) next = { ...next, audit: p as AuditPublic };
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
  const arrived = { ...state.arrived, [iv.id]: wall };
  const started = state.session?.started_at ? Date.parse(state.session.started_at) : Number.NaN;
  if (Number.isFinite(started) && iv.t < wall - started - HISTORY_MS) {
    return { ...state, interventions, arrived, shown: [...state.shown, iv.id] };
  }
  if (state.streamingId === null) {
    return { ...state, interventions, arrived, shown: [...state.shown, iv.id], streamingId: iv.id };
  }
  return { ...state, interventions, arrived, pending: [...state.pending, iv.id] };
}

/** Add one model.activity event; a call's "started" and its ending both stay, a repeat of either doesn't. */
function addActivity(list: ActivityEvent[], e: ActivityEvent): ActivityEvent[] {
  if (list.some((x) => x.call_id === e.call_id && x.status === e.status)) return list;
  return [...list, e];
}

/** Record when something first reached this browser over the socket (not when it came from history). */
function stamp(arrived: Record<string, number>, key: string, wall: number): Record<string, number> {
  return key in arrived ? arrived : { ...arrived, [key]: wall };
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
  if ((msg as { type: string }).type === "model.activity") {
    const activity = (msg as unknown as ModelActivityMsg).activity;
    return { ...state, activity: addActivity(state.activity, { ...activity, wall: action.wall }) };
  }
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
      return {
        ...state,
        runs: upsert(state.runs, msg.result, (x) => x.run_id),
        arrived: stamp(state.arrived, `run:${msg.result.run_id}`, action.wall),
      };
    case "notes.update":
      return { ...state, notes: { steps: msg.steps, issues: msg.issues, stated_plan: msg.stated_plan } };
    case "integrity.flag":
      return { ...state, flags: upsert(state.flags, msg.flag, (x) => x.id) };
    case "defense.audit":
      return { ...state, audit: msg.audit, arrived: stamp(state.arrived, "audit", action.wall) };
    case "defense.chaos.metric":
      return { ...state, metrics: upsert(state.metrics, msg.metric, (x) => `${x.run_id}:${x.t_ms}`) };
    case "defense.chaos.done":
      return {
        ...state,
        chaosRuns: upsert(state.chaosRuns, msg.run, (x) => x.id),
        arrived: stamp(state.arrived, `chaos:${msg.run.id}`, action.wall),
      };
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
    let live = true;
    let s: SessionSocket | null = null;
    // The socket only resends session.state, so what happened before this socket attached (a reload, a
    // drop) comes from the public timeline. It's loaded on every open, after the server has the socket, so
    // nothing falls between the two; upserts drop the overlap. A brand-new session has no history.
    const loadHistory = () =>
      api
        .timeline(id)
        .then((events) => live && dispatch({ type: "history", events }))
        .catch(() => {});
    // Connect a tick later: a mount that's undone at once (React's dev double mount) then never opens a
    // socket. The server starts the session on the first connect, and its opening lines would go to a
    // socket that's about to close.
    const start = window.setTimeout(() => {
      s = connectSession(id, {
        onMessage: (msg) => dispatch({ type: "msg", msg, at: performance.now(), wall: Date.now() }),
        onStatus: (status) => dispatch({ type: "status", status }),
        onOpen: () => void loadHistory(),
      });
      socket.current = s;
    }, 0);
    return () => {
      live = false;
      window.clearTimeout(start);
      socket.current = null;
      s?.close();
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

/** The session is over: ended, its report being written, written, or failed (#47). */
export function isFinished(phase: Phase | null): boolean {
  return phase === "ended" || phase === "reporting" || phase === "reported" || phase === "failed";
}

/** Seconds left, counting down locally between the server's session.state updates. */
export function useRemaining(state: LiveState): number | null {
  const [now, setNow] = useState(0);
  const live = state.remainingS !== null && !isFinished(state.phase);
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

/** Date.now(), ticking once a second while `active` (wait timers, the grill countdown); 0 when inactive. */
export function useClock(active: boolean): number {
  const [now, setNow] = useState(0);
  useEffect(() => {
    if (!active) return;
    const tick = () => setNow(Date.now());
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [active]);
  return active ? now : 0;
}

// The server's limits on what a client sends (PR #38, PLAN §8.2): longer is rejected with `bad_message`.
export const CHAT_MAX = 4_000;
export const CODE_MAX = 200_000;
export const VERIFY_MAX_FILES = 60;

/** An `error` message as one line for the candidate; the socket's own limit codes get plain words. */
export function socketErrorText(err: ErrorMsg): string {
  switch (err.code) {
    case "rate_limited":
      return "You're sending faster than the server accepts. Give it a moment.";
    case "too_large":
      return "That was too large to send. Shorten it and try again.";
    default:
      return err.message;
  }
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
