"use client";

import { useRef } from "react";
import { MIC_LABEL, type MicState } from "./useMic";

const NOTE: Record<MicState, string> = {
  off: "Speech to text: talk through your approach instead of typing.",
  starting: "Asking for your microphone…",
  live: "Listening. What you say is transcribed for the interviewer.",
  stopped: "Speech to text: talk through your approach instead of typing.",
  error: "Voice isn't available right now. Use the chat box.",
};

// The mic bar above the chat box: turn speech to text on or off, and Hold to Ask while it's on.
export function MicControls({
  mic,
  onToggle,
  onAsking,
  disabled = false,
}: {
  mic: MicState;
  onToggle: () => void;
  onAsking: (holding: boolean) => void;
  disabled?: boolean;
}) {
  const holding = useRef(false);
  const hold = (next: boolean) => {
    if (holding.current === next) return;
    holding.current = next;
    onAsking(next);
  };

  return (
    <div className="rm-voice">
      <button
        type="button"
        className={mic === "live" ? "ui-btn ui-btn-primary" : "ui-btn"}
        aria-pressed={mic === "live"}
        onClick={onToggle}
        disabled={disabled || mic === "starting"}
      >
        {MIC_LABEL[mic]}
      </button>
      {mic === "live" && (
        <button
          type="button"
          className="ui-btn"
          onPointerDown={() => hold(true)}
          onPointerUp={() => hold(false)}
          onPointerLeave={() => hold(false)}
          onKeyDown={(e) => (e.key === " " || e.key === "Enter") && !e.repeat && hold(true)}
          onKeyUp={(e) => (e.key === " " || e.key === "Enter") && hold(false)}
          disabled={disabled}
        >
          Hold to Ask
        </button>
      )}
      <span className="rm-voice-note" aria-live="polite">
        {NOTE[mic]}
      </span>
    </div>
  );
}
