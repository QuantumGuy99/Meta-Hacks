"use client";

import { voiceLabel } from "@/lib/tts";
import type { Voice } from "./useVoice";

// The header's voice controls (PLAN §14.7): mute and the voice picker, or "Turn On Voice" when the browser won't
// speak until the candidate clicks. Nothing shows without speechSynthesis or English voices.
export function VoiceControls({ voice }: { voice: Voice }) {
  if (!voice.blocked && voice.voices.length === 0) return null;
  return (
    <span className="rm-tts">
      {voice.blocked ? (
        <button type="button" className="ui-btn ui-btn-primary" onClick={voice.unlock}>
          Turn On Voice
        </button>
      ) : (
        <button type="button" className="ui-btn" aria-pressed={voice.muted} onClick={voice.toggleMute}>
          Mute Voice
        </button>
      )}
      {voice.voices.length > 1 && (
        <select
          aria-label="Interviewer voice"
          value={voice.voice?.name ?? ""}
          onChange={(e) => voice.chooseVoice(e.target.value || null)}
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

/** One line under the feed when the best voice installed sounds robotic. */
export function VoiceHint({ voice }: { voice: Voice }) {
  if (!voice.plainVoice || voice.muted) return null;
  return (
    <p className="rm-tts-hint">
      For a more natural voice, use Microsoft Edge, or on a Mac add a Premium voice in System Settings → Accessibility →
      Spoken Content.
    </p>
  );
}
