"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { WS_URL } from "@/lib/api";
import { startAudioCapture, type AudioCapture, type AudioState } from "@/lib/capture/audio";

export type MicState = "off" | AudioState;

// The candidate's microphone streams to the session's audio socket, the server transcribes it (Muse Voice
// Transcribe, PLAN §8.3) and the turns come back on the session socket as transcript.update. While the
// interviewer's voice plays (useVoice), the mic sends silence instead, so it isn't transcribed.
export function useMic(id: string) {
  const [mic, setMic] = useState<MicState>("off");
  const capture = useRef<AudioCapture | null>(null);
  const paused = useRef(false); // kept for a mic turned on while the interviewer is talking

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
      capture.current.setPaused(paused.current);
    } catch {
      capture.current = null;
      setMic("error");
    }
  }, [id]);

  /** Hold to Ask: what the candidate says while holding it is a question for the interviewer. */
  const setAsking = useCallback((holding: boolean) => capture.current?.setAsking(holding), []);

  /** Silence the mic while the interviewer speaks (the stream keeps its pace, §8.3). */
  const setPaused = useCallback((next: boolean) => {
    paused.current = next;
    capture.current?.setPaused(next);
  }, []);

  useEffect(() => () => capture.current?.stop(), []);

  return { mic, toggleMic, setAsking, setPaused };
}

export const MIC_LABEL: Record<MicState, string> = {
  off: "Turn On Mic",
  starting: "Starting Mic…",
  live: "Mic On",
  stopped: "Turn On Mic",
  error: "Mic Unavailable",
};
