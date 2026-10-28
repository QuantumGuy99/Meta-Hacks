"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { LiveState } from "@/lib/session";
import { createTts, type Tts } from "@/lib/tts";

// After the last word the mic stays silent a moment longer, so the tail of the interviewer's voice in the room
// isn't transcribed as the candidate.
const TAIL_MS = 300;

const noSubscribe = () => () => {};

function clearTimer(timer: { current: number | null }) {
  if (timer.current !== null) window.clearTimeout(timer.current);
  timer.current = null;
}

// The interviewer's voice in a live room (PLAN §14.7): each new interviewer message with `speak: true` is read
// aloud as it appears, unless the session turned spoken replies off or the candidate muted it. While it speaks,
// `setPaused(true)` makes the mic send silence (§8.3), so the server never transcribes the interviewer.
export function useVoice(state: LiveState, setPaused: (paused: boolean) => void) {
  const [speaking, setSpeaking] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [muted, setMutedState] = useState(false);
  const supported = useSyncExternalStore(noSubscribe, () => "speechSynthesis" in window, () => false);
  const tts = useRef<Tts | null>(null);
  const tail = useRef<number | null>(null);
  const pause = useRef(setPaused);
  useEffect(() => {
    pause.current = setPaused;
  });

  useEffect(() => {
    const t = createTts({
      onStart: () => {
        clearTimer(tail);
        pause.current(true);
        setSpeaking(true);
      },
      onEnd: () => {
        setSpeaking(false);
        clearTimer(tail);
        tail.current = window.setTimeout(() => pause.current(false), TAIL_MS);
      },
      onBlocked: setBlocked,
    });
    tts.current = t;
    return () => {
      t.dispose();
      clearTimer(tail);
      tts.current = null;
    };
  }, []);

  // Speak a message when it starts streaming into the feed: only live ones stream, so nothing loaded from
  // the timeline after a reload is read out again.
  const spoken = useRef(new Set<string>());
  const speakReplies = state.session?.config.speak_replies !== false;
  useEffect(() => {
    const id = state.streamingId;
    if (!id || spoken.current.has(id)) return;
    spoken.current.add(id);
    const iv = state.interventions.find((x) => x.id === id);
    if (iv?.speak && speakReplies) tts.current?.speak(iv.text);
  }, [state.streamingId, state.interventions, speakReplies]);

  /** Barge-in (the candidate holds Ask) or skipping: stop now and give the mic back at once. */
  const interrupt = useCallback(() => {
    tts.current?.cancel();
    clearTimer(tail);
    pause.current(false);
  }, []);

  const setMuted = useCallback(
    (next: boolean) => {
      setMutedState(next);
      tts.current?.setMuted(next);
      if (next) interrupt();
    },
    [interrupt],
  );

  /** From a click: the browser lets the page speak from now on, starting with the message it held back. */
  const unlock = useCallback(() => tts.current?.unlock(), []);

  return {
    /** Show the voice controls: the browser can speak and the session reads replies aloud. */
    available: supported && state.session !== null && speakReplies,
    speaking,
    blocked: blocked && !muted,
    muted,
    setMuted,
    unlock,
    interrupt,
  };
}

export type Voice = ReturnType<typeof useVoice>;
