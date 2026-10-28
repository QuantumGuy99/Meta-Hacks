// Spoken interviewer replies with the browser's speechSynthesis (PLAN §14.7): one queue, a natural English voice
// when there is one, cancel() for barge-in, and start/end callbacks that drive the speaking indicator.

type Handlers = { onStart?: () => void; onEnd?: () => void };

const supported = () => typeof window !== "undefined" && "speechSynthesis" in window;

function pickVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith("en"));
  return (
    voices.find((v) => /natural|neural|google/i.test(v.name)) ?? voices.find((v) => v.default) ?? voices[0] ?? null
  );
}

/** Queue `text`; the browser speaks queued utterances in order. */
export function speak(text: string, handlers: Handlers = {}): void {
  if (!supported() || !text.trim()) return;
  const u = new SpeechSynthesisUtterance(text);
  const voice = pickVoice();
  if (voice) u.voice = voice;
  u.rate = 1.02;
  u.onstart = () => handlers.onStart?.();
  u.onend = () => handlers.onEnd?.();
  u.onerror = () => handlers.onEnd?.();
  window.speechSynthesis.speak(u);
}

/** Stop speaking now and drop the queue (the candidate started talking, or left the room). */
export function cancelSpeech(): void {
  if (supported()) window.speechSynthesis.cancel();
}
