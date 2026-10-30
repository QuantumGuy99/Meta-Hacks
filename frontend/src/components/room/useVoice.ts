"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { LiveState } from "@/lib/session";
import {
  createTts,
  isNaturalVoice,
  loadVoiceChoice,
  saveVoiceChoice,
  type Tts,
  type VoiceLike,
} from "@/lib/tts";

// After the last word the mic stays silent a moment longer, so the tail of the interviewer's voice in the room
// isn't transcribed as the candidate.
const TAIL_MS = 300;
// What a newly picked voice says, so the candidate hears it.
const SAMPLE = "Hi, this is how I'll sound.";
const HINT_KEY = "ares.voiceHint"; // "dismissed" once the candidate closes the better-voice hint

const noSubscribe = () => () => {};

function clearTimer(timer: { current: number | null }) {
  if (timer.current !== null) window.clearTimeout(timer.current);
  timer.current = null;
}

// The hint's dismissal lives in localStorage; a tiny store so every room re-renders when it changes.
const hintListeners = new Set<() => void>();
const subscribeHint = (listener: () => void) => {
  hintListeners.add(listener);
  return () => hintListeners.delete(listener);
};
const hintDismissed = () => {
  try {
    return window.localStorage.getItem(HINT_KEY) === "dismissed";
  } catch {
    return false;
  }
};
const dismissHint = () => {
  try {
    window.localStorage.setItem(HINT_KEY, "dismissed");
  } catch {
    // storage blocked: the hint goes away for this page only
  }
  hintListeners.forEach((listener) => listener());
};

// The interviewer's voice in a live room (PLAN §14.7): each new interviewer message with `speak: true` is read
// aloud as it appears, unless the session turned spoken replies off or the candidate muted it. While it speaks,
// `setPaused(true)` makes the mic send silence (§8.3), so the server never transcribes the interviewer.
export function useVoice(state: LiveState, setPaused: (paused: boolean) => void) {
  const [speaking, setSpeaking] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [muted, setMutedState] = useState(false);
  const [voices, setVoices] = useState<VoiceLike[]>([]);
  const [voice, setVoiceState] = useState<VoiceLike | null>(null);
  const [hintClosed, setHintClosed] = useState(false);
  const supported = useSyncExternalStore(noSubscribe, () => "speechSynthesis" in window, () => false);
  const hintStored = useSyncExternalStore(subscribeHint, hintDismissed, () => true);
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
      onVoices: (list, current) => {
        setVoices(list);
        setVoiceState(current);
      },
      voiceName: loadVoiceChoice(),
    });
    tts.current = t;
    // Wake the speech engine so the first line doesn't lag: now if the page already had a click (the setup
    // form's Start), else on the first click or key press here.
    const warm = () => t.warm();
    if (navigator.userActivation?.hasBeenActive) warm();
    document.addEventListener("pointerdown", warm, { once: true });
    document.addEventListener("keydown", warm, { once: true });
    return () => {
      document.removeEventListener("pointerdown", warm);
      document.removeEventListener("keydown", warm);
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

  /** The picker: use this voice from the next sentence on, remember it in this browser, and let it say hello
   * when the interviewer isn't talking. */
  const setVoice = useCallback((name: string) => {
    const t = tts.current;
    if (!t) return;
    t.setVoice(name);
    saveVoiceChoice(name);
    if (!t.speaking) t.speak(SAMPLE);
  }, []);

  /** From a click: the browser lets the page speak from now on, starting with the message it held back. */
  const unlock = useCallback(() => tts.current?.unlock(), []);

  const closeHint = useCallback(() => {
    setHintClosed(true);
    dismissHint();
  }, []);

  const available = supported && state.session !== null && speakReplies;
  return {
    /** Show the voice controls: the browser can speak and the session reads replies aloud. */
    available,
    speaking,
    blocked: blocked && !muted,
    muted,
    setMuted,
    /** The English voices, most human first, and the one in use. */
    voices,
    voice,
    setVoice,
    /** The best voice installed is Google's or older: suggest a more natural one, until it's dismissed. */
    hint: available && !muted && voices.length > 0 && !isNaturalVoice(voices[0]) && !hintStored && !hintClosed,
    closeHint,
    unlock,
    interrupt,
  };
}

export type Voice = ReturnType<typeof useVoice>;
