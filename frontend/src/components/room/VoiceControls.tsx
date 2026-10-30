"use client";

import { voiceLabel } from "@/lib/tts";
import type { Voice } from "./useVoice";

// The room header's voice controls: mute or unmute the interviewer's spoken replies and pick its voice, or
// "Turn On Voice" when the browser held speech back until the candidate clicks something (autoplay rules).
export function VoiceControls({ voice }: { voice: Voice }) {
  if (!voice.available) return null;
  if (voice.blocked) {
    return (
      <button type="button" className="ui-btn ui-btn-primary" onClick={voice.unlock} title="Your browser waits for a click before it speaks">
        Turn On Voice
      </button>
    );
  }
  return (
    <span className="rm-voice-ctl">
      <button
        type="button"
        className="ui-btn"
        aria-pressed={!voice.muted}
        onClick={() => voice.setMuted(!voice.muted)}
        title={voice.muted ? "Read the interviewer's replies aloud" : "Stop reading the interviewer's replies aloud"}
      >
        {voice.muted ? "Voice Off" : "Voice On"}
      </button>
      {voice.voices.length > 0 && (
        <select
          className="rm-voice-pick"
          aria-label="Interviewer's voice"
          value={voice.voice?.name ?? ""}
          onChange={(e) => voice.setVoice(e.target.value)}
          disabled={voice.muted}
        >
          {voice.voices.map((v) => (
            <option key={v.name} value={v.name}>
              {voiceLabel(v)}
            </option>
          ))}
        </select>
      )}
    </span>
  );
}

// One line under the header when the best voice installed is Google's or older.
export function VoiceHint({ voice }: { voice: Voice }) {
  if (!voice.hint) return null;
  return (
    <p className="rm-voice-hint" role="note">
      <span>
        For a more natural voice, open this in Microsoft Edge, or add a Premium voice in macOS System Settings →
        Accessibility → Spoken Content.
      </span>
      <button type="button" className="rm-voice-hint-close" onClick={voice.closeHint} aria-label="Dismiss the voice hint">
        ×
      </button>
    </p>
  );
}
