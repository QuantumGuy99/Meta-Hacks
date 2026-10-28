"use client";

import type { Voice } from "./useVoice";

// The room header's voice button: mute or unmute the interviewer's spoken replies, or "Turn On Voice" when the
// browser held speech back until the candidate clicks something (autoplay rules).
export function VoiceToggle({ voice }: { voice: Voice }) {
  if (!voice.available) return null;
  if (voice.blocked) {
    return (
      <button type="button" className="ui-btn ui-btn-primary" onClick={voice.unlock} title="Your browser waits for a click before it speaks">
        Turn On Voice
      </button>
    );
  }
  return (
    <button
      type="button"
      className="ui-btn"
      aria-pressed={!voice.muted}
      onClick={() => voice.setMuted(!voice.muted)}
      title={voice.muted ? "Read the interviewer's replies aloud" : "Stop reading the interviewer's replies aloud"}
    >
      {voice.muted ? "Voice Off" : "Voice On"}
    </button>
  );
}
