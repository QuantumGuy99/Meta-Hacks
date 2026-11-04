"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL } from "@/lib/api";
import type { LiveState } from "@/lib/session";
import {
  createVoice,
  isNaturalVoice,
  loadVoiceChoice,
  saveVoiceChoice,
  type Voice as Speaker,
  type VoiceLike,
} from "@/lib/tts";

// The interviewer's voice in a live room (PLAN §14.7). Each new interviewer message the server marks `speak` is
// read aloud as it appears in the feed: by the server voice (ElevenLabs through the backend, #80) when it answers
// in time, else by the browser voice. `onSpeaking` tells the mic to send silence until it's done (§8.3), so the
// interviewer isn't transcribed as the candidate. Messages a reload brings back are never spoken: only the one
// streaming into the feed is, and history doesn't stream.
export function useVoice(state: LiveState, onSpeaking: (speaking: boolean) => void, sessionId: string) {
  const tts = useRef<Speaker | null>(null);
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
  // Whether the server voice is still in use: it is until it fails twice in a row (no key, or errors), and the
  // voice reports that as each run of lines ends.
  const [server, setServer] = useState(true);

  useEffect(() => {
    const t = createVoice({
      speechUrl: (id) => `${API_URL}/api/sessions/${encodeURIComponent(sessionId)}/speech/${encodeURIComponent(id)}`,
      onStart: () => {
        setSpeaking(true);
        notify.current(true);
      },
      onEnd: () => {
        setSpeaking(false);
        notify.current(false);
        setServer(t.server);
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
    // A line the browser refused (no click on this page yet, e.g. after a reload) waits for one. Any click or key
    // releases it, not only the voice hint's button: otherwise every later line queued behind it stayed silent.
    const release = () => {
      if (t.blocked) t.unlock();
    };
    window.addEventListener("pointerdown", release);
    window.addEventListener("keydown", release);
    return () => {
      window.removeEventListener("pointerdown", wake);
      window.removeEventListener("pointerdown", release);
      window.removeEventListener("keydown", release);
      t.dispose();
      if (tts.current === t) tts.current = null;
    };
  }, [sessionId]);

  const live = state.streamingId;
  useEffect(() => {
    if (!live || spoken.current.has(live)) return;
    spoken.current.add(live);
    const iv = state.interventions.find((x) => x.id === live);
    if (iv?.speak) tts.current?.speak(iv.text, iv.id);
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
    /** The browser voice is reading and the best one installed is Google's or older: suggest a more natural one. */
    plainVoice: !server && voices.length > 0 && !isNaturalVoice(voices[0]),
    toggleMute,
    chooseVoice,
    unlock,
    cancel,
  };
}

export type Voice = ReturnType<typeof useVoice>;
