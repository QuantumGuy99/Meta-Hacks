"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { WS_URL } from "@/lib/api";
import { startAudioCapture, type AudioCapture, type AudioState } from "@/lib/capture/audio";

export type MicState = "off" | AudioState;

// Speech to text in a live room: the candidate's microphone streams to the session's audio socket, the server
// transcribes it (Muse Voice Transcribe, PLAN §8.3) and the turns come back on the session socket as
// transcript.update. While the interviewer speaks (useVoice), the mic is paused and sends silence instead.
export function useMic(id: string) {
  const [mic, setMic] = useState<MicState>("off");
  const capture = useRef<AudioCapture | null>(null);
  // Paused while the interviewer speaks; a mic turned on mid-sentence starts paused too.
  const paused = useRef(false);

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

  /** True while the interviewer speaks: the mic sends silence, so the server doesn't transcribe its voice. */
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
