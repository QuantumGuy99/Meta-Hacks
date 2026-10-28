"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { WS_URL } from "@/lib/api";
import { startAudioCapture, type AudioCapture, type AudioState } from "@/lib/capture/audio";

export type MicState = "off" | AudioState;

// Voice in a live room is speech to text only: the candidate's microphone streams to the session's audio
// socket, the server transcribes it (Muse Voice Transcribe, PLAN §8.3) and the turns come back on the
// session socket as transcript.update. The interviewer's replies stay text; nothing is read aloud.
export function useMic(id: string) {
  const [mic, setMic] = useState<MicState>("off");
  const capture = useRef<AudioCapture | null>(null);

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

  /** Hold to Ask: what the candidate says while holding it is a question for the interviewer. */
  const setAsking = useCallback((holding: boolean) => capture.current?.setAsking(holding), []);

  useEffect(() => () => capture.current?.stop(), []);

  return { mic, toggleMic, setAsking };
}

export const MIC_LABEL: Record<MicState, string> = {
  off: "Turn On Mic",
  starting: "Starting Mic…",
  live: "Mic On",
  stopped: "Turn On Mic",
  error: "Mic Unavailable",
};
