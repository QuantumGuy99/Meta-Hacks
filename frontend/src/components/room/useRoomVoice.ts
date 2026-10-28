"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { WS_URL } from "@/lib/api";
import { startAudioCapture, type AudioCapture, type AudioState } from "@/lib/capture/audio";
import type { LiveState } from "@/lib/session";
import { cancelSpeech, speak } from "@/lib/tts";

export type MicState = "off" | AudioState;

// Voice in a live room: reads each new interviewer message aloud when the session asks for spoken replies,
// and runs the microphone on the session's audio socket. The mic sends silence while the interviewer speaks
// (PLAN §8.3), and talking over the interviewer stops its speech (barge-in).
export function useRoomVoice(id: string, state: LiveState, caption: string | null) {
  const [speaking, setSpeaking] = useState(false);
  const [mic, setMic] = useState<MicState>("off");
  const capture = useRef<AudioCapture | null>(null);
  const speakReplies = state.session?.config.speak_replies ?? false;

  // Speak the message that just started streaming.
  useEffect(() => {
    const iv = state.interventions.find((x) => x.id === state.streamingId);
    if (!iv || !speakReplies || !iv.speak) return;
    speak(iv.text, { onStart: () => setSpeaking(true), onEnd: () => setSpeaking(false) });
  }, [state.streamingId, state.interventions, speakReplies]);

  useEffect(() => {
    capture.current?.setPaused(speaking);
  }, [speaking]);

  // Barge-in: the candidate started talking.
  useEffect(() => {
    if (caption) cancelSpeech();
  }, [caption]);

  const toggleMic = useCallback(async () => {
    if (capture.current) {
      capture.current.stop();
      capture.current = null;
      return;
    }
    try {
      capture.current = await startAudioCapture({
        wsUrl: `${WS_URL}/ws/sessions/${encodeURIComponent(id)}/audio`,
        onState: (s) => {
          setMic(s);
          if (s === "error" || s === "stopped") capture.current = null;
        },
      });
    } catch {
      capture.current = null;
      setMic("error");
    }
  }, [id]);

  useEffect(
    () => () => {
      capture.current?.stop();
      cancelSpeech();
    },
    [],
  );

  return { speaking, mic, toggleMic };
}

export const MIC_LABEL: Record<MicState, string> = {
  off: "Mic Off",
  starting: "Mic…",
  live: "Mic On",
  stopped: "Mic Off",
  error: "Mic Unavailable",
};
