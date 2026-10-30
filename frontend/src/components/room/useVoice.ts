"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { LiveState } from "@/lib/session";
import { createTts, isNaturalVoice, loadVoiceChoice, saveVoiceChoice, type Tts, type VoiceLike } from "@/lib/tts";

// The interviewer's voice in a live room (PLAN §14.7). Each new interviewer message the server marks `speak` is
// read aloud as it appears in the feed, and `onSpeaking` tells the mic to send silence until it's done (§8.3), so
// the interviewer isn't transcribed as the candidate. Messages a reload brings back are never spoken: only the
// one streaming into the feed is, and history doesn't stream.
export function useVoice(state: LiveState, onSpeaking: (speaking: boolean) => void) {
  const tts = useRef<Tts | null>(null);
  const spoken = useRef(new Set<string>());
  const notify = useRef(onSpeaking);
  useEffect(() => {
    notify.current = onSpeaking;
  });
  const [speaking, setSpeaking] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [muted, setMuted] = useState(false);
  const [voices, setVoices] = useState<VoiceLike[]>([]);
  const [voice, setVoice] = useState<VoiceLike | null>(null);

  useEffect(() => {
    const t = createTts({
      onStart: () => {
        setSpeaking(true);
        notify.current(true);
      },
      onEnd: () => {
        setSpeaking(false);
        notify.current(false);
      },
      onBlocked: setBlocked,
      onVoices: (list, v) => {
        setVoices(list);
        setVoice(v);
      },
      voiceName: loadVoiceChoice(),
    });
    tts.current = t;
    // Start the engine now, and again on the first click (which also lets browsers that need a gesture speak).
    t.warm();
    const wake = () => t.warm();
    window.addEventListener("pointerdown", wake, { once: true });
    return () => {
      window.removeEventListener("pointerdown", wake);
      t.dispose();
      if (tts.current === t) tts.current = null;
    };
  }, []);

  const live = state.streamingId;
  useEffect(() => {
    if (!live || spoken.current.has(live)) return;
    spoken.current.add(live);
    const iv = state.interventions.find((x) => x.id === live);
    if (iv?.speak) tts.current?.speak(iv.text);
  }, [live, state.interventions]);

  const toggleMute = useCallback(() => {
    const next = !muted;
    tts.current?.setMuted(next);
    setMuted(next);
  }, [muted]);

  const chooseVoice = useCallback((name: string | null) => {
    saveVoiceChoice(name);
    tts.current?.setVoice(name);
  }, []);

  const unlock = useCallback(() => tts.current?.unlock(), []);
  /** Barge-in: stop talking and drop the queue (Hold to Ask). */
  const cancel = useCallback(() => tts.current?.cancel(), []);

  return {
    speaking,
    blocked,
    muted,
    voices,
    voice,
    /** The best voice installed is Google's or older: suggest a more natural one. */
    plainVoice: voices.length > 0 && !isNaturalVoice(voices[0]),
    toggleMute,
    chooseVoice,
    unlock,
    cancel,
  };
}

export type Voice = ReturnType<typeof useVoice>;
