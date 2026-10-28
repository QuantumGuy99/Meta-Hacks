// The interviewer's voice: browser text to speech with speechSynthesis (PLAN §14.7). Meta has no TTS model and
// third-party TTS is ruled out, so this is the only voice out. Text is spoken as a queue of short chunks
// (Chrome cuts an utterance off after about 15 s), in a natural English voice when the browser has one.
// onStart/onEnd drive the speaking indicator and the mic's silence (§8.3), cancel() is the barge-in.
// Keep this file free of TypeScript-only runtime syntax (enums, namespaces) so Node can run its tests with type
// stripping. The browser parts sit behind `SpeechDeps`, so tests fake them; without speechSynthesis (old
// browsers, the server render) every call is a no-op.

export const MAX_CHUNK_CHARS = 180; // about 12 s of speech, under Chrome's cut-off
export const VOICES_WAIT_MS = 1_500; // some browsers never fire voiceschanged: speak in the default voice after this
export const STALL_CHECK_MS = 1_000; // how often to look for a chunk whose end event never came

/** Voice names in order of preference (English voices only): Edge's neural voices, Chrome's, then macOS's. */
const PREFERRED_VOICES = [/\bnatural\b/i, /^google us english$/i, /^samantha\b/i];

export interface Tts {
  /** False when the browser has no speechSynthesis: every call is then a no-op. */
  readonly supported: boolean;
  /** Between onStart and onEnd. */
  readonly speaking: boolean;
  /** The browser refused to speak before the user interacted with the page; `unlock()` from a click fixes it. */
  readonly blocked: boolean;
  /** Queue `text` after anything still being said. Markdown is read as plain text and code blocks are skipped. */
  speak(text: string): void;
  /** Stop now and drop the queue (barge-in, skipping, leaving the room). onEnd fires if speech was playing. */
  cancel(): void;
  /** Muting stops the current speech, and `speak()` does nothing until it's unmuted. */
  setMuted(muted: boolean): void;
  /** Call from a click handler: speaks what was blocked (or nothing) while the browser allows it. */
  unlock(): void;
  dispose(): void;
}

export interface TtsOptions {
  onStart?: () => void;
  onEnd?: () => void;
  onBlocked?: (blocked: boolean) => void;
  rate?: number;
}

/** What `createTts` needs from the browser. */
export interface SpeechDeps {
  synth: SynthLike;
  makeUtterance(text: string): UtteranceLike;
}

export interface SynthLike {
  readonly speaking: boolean;
  readonly pending: boolean;
  readonly paused: boolean;
  getVoices(): VoiceLike[];
  speak(utterance: UtteranceLike): void;
  cancel(): void;
  resume(): void;
  addEventListener(type: "voiceschanged", listener: () => void): void;
  removeEventListener(type: "voiceschanged", listener: () => void): void;
}

export interface VoiceLike {
  name: string;
  lang: string;
  default: boolean;
}

export interface UtteranceLike {
  text: string;
  lang: string;
  voice: VoiceLike | null;
  rate: number;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
}

const NO_TTS: Tts = {
  supported: false,
  speaking: false,
  blocked: false,
  speak() {},
  cancel() {},
  setMuted() {},
  unlock() {},
  dispose() {},
};

export function createTts(opts: TtsOptions = {}, deps: SpeechDeps | null = browserSpeech()): Tts {
  if (!deps) return NO_TTS;
  const { synth, makeUtterance } = deps;
  let voice: VoiceLike | null = null;
  let voicesReady = false;
  let queue: string[] = [];
  let current: UtteranceLike | null = null;
  let started = false; // the current chunk fired onstart
  let speaking = false;
  let blocked = false;
  let muted = false;
  let disposed = false;
  let stallTimer: ReturnType<typeof setTimeout> | null = null;
  let voicesTimer: ReturnType<typeof setTimeout> | null = null;

  const setBlocked = (next: boolean) => {
    if (blocked === next) return;
    blocked = next;
    opts.onBlocked?.(next);
  };
  const stopSpeaking = () => {
    if (!speaking) return;
    speaking = false;
    opts.onEnd?.();
  };
  const clearStall = () => {
    if (stallTimer !== null) clearTimeout(stallTimer);
    stallTimer = null;
  };

  // The current chunk is over (ended, failed or lost): say the next one, or report the end.
  const advance = () => {
    current = null;
    started = false;
    clearStall();
    if (queue.length) pump();
    else stopSpeaking();
  };

  // The browser wouldn't speak without a user gesture: hold this message for unlock() and stop.
  const hold = (chunk: string) => {
    queue = [chunk, ...queue];
    current = null;
    started = false;
    clearStall();
    stopSpeaking();
    setBlocked(true);
  };

  const pump = () => {
    if (disposed || muted || current || !voicesReady) return;
    const chunk = queue.shift();
    if (chunk === undefined) return;
    const u = makeUtterance(chunk);
    u.voice = voice;
    u.lang = voice?.lang ?? "en-US";
    u.rate = opts.rate ?? 1;
    // Events from a chunk that was cancelled or let go (u !== current) are ignored.
    u.onstart = () => {
      if (u !== current) return;
      started = true;
      setBlocked(false);
      if (!speaking) {
        speaking = true;
        opts.onStart?.();
      }
    };
    u.onend = () => {
      if (u === current) advance();
    };
    u.onerror = (e) => {
      if (u !== current) return;
      if (e.error === "not-allowed") hold(chunk);
      else advance(); // interrupted by someone else, or a synthesis error: skip this chunk
    };
    current = u;
    started = false;
    if (synth.paused) synth.resume(); // Chrome can stay paused after a tab switch
    synth.speak(u);
    watch(u, chunk, Date.now());
  };

  // Chrome sometimes never fires end (or gets stuck speaking). Once the engine is idle, a chunk that started
  // has ended; one that never started was refused (Safari refuses without an error). A chunk running far past
  // its length is cut so the mic isn't held silent for good.
  const watch = (u: UtteranceLike, chunk: string, since: number) => {
    stallTimer = setTimeout(() => {
      if (u !== current) return;
      if (!synth.speaking && !synth.pending) {
        if (started) advance();
        else hold(chunk);
      } else if (Date.now() - since > 5_000 + chunk.length * 150) {
        current = null;
        synth.cancel();
        advance();
      } else {
        watch(u, chunk, since);
      }
    }, STALL_CHECK_MS);
  };

  const onVoices = () => {
    const list = synth.getVoices();
    if (!list.length) return;
    voice = pickVoice(list); // re-picked on every change: Chrome adds its network voices after the local ones
    if (!voicesReady) {
      voicesReady = true;
      if (voicesTimer !== null) clearTimeout(voicesTimer);
      pump();
    }
  };
  synth.addEventListener("voiceschanged", onVoices);
  onVoices();
  if (!voicesReady) {
    voicesTimer = setTimeout(() => {
      voicesReady = true;
      pump();
    }, VOICES_WAIT_MS);
  }

  const cancel = () => {
    queue = [];
    const wasCurrent = current;
    current = null;
    started = false;
    clearStall();
    if (wasCurrent || synth.speaking || synth.pending) synth.cancel();
    stopSpeaking();
  };

  return {
    supported: true,
    get speaking() {
      return speaking;
    },
    get blocked() {
      return blocked;
    },
    speak(text) {
      if (disposed || muted) return;
      const chunks = splitSpeech(text);
      if (!chunks.length) return;
      // While blocked, only the newest message waits for unlock(): a backlog of old ones would be stale.
      queue = blocked && !current ? chunks : [...queue, ...chunks];
      pump();
    },
    cancel,
    setMuted(next) {
      muted = next;
      if (next) cancel();
    },
    unlock() {
      if (disposed || muted) return;
      if (queue.length && !current) pump();
      // Nothing held: an empty utterance inside the click still unlocks speech for later messages.
      else if (!current) synth.speak(makeUtterance(""));
    },
    dispose() {
      if (disposed) return;
      cancel();
      disposed = true;
      synth.removeEventListener("voiceschanged", onVoices);
      if (voicesTimer !== null) clearTimeout(voicesTimer);
    },
  };
}

/** The best English voice: a preferred name (en-US first), else the default English voice, else any English. */
export function pickVoice(voices: VoiceLike[]): VoiceLike | null {
  const isUs = (v: VoiceLike) => /^en[-_]us$/i.test(v.lang);
  const english = voices
    .filter((v) => /^en([-_]|$)/i.test(v.lang))
    .sort((a, b) => Number(isUs(b)) - Number(isUs(a)));
  for (const pattern of PREFERRED_VOICES) {
    const match = english.find((v) => pattern.test(v.name));
    if (match) return match;
  }
  return english.find((v) => v.default) ?? english[0] ?? null;
}

/** Markdown as it should sound: code blocks skipped, markers and link targets dropped, identifiers spaced. */
export function speakable(text: string): string {
  return text
    .replace(/```[\s\S]*?(```|$)/g, " ")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/^\s{0,3}(#{1,6}|>|[-*+])\s+/gm, "")
    .replace(/[*~]+/g, "")
    .replace(/(\w)_(?=\w)/g, "$1 ")
    .replace(/(^|\s)_+|_+(?=\s|[.,!?;:]|$)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

/** `text` as chunks of at most `max` characters: whole sentences packed together, and a sentence that's too
 * long split at commas, then at spaces. */
export function splitSpeech(text: string, max = MAX_CHUNK_CHARS): string[] {
  const clean = speakable(text);
  if (!clean) return [];
  const pieces: string[] = [];
  for (const sentence of clean.split(/(?<=[.!?]["')\]]?)\s+/)) {
    if (sentence.length <= max) {
      pieces.push(sentence);
      continue;
    }
    for (const clause of sentence.split(/(?<=[,;:])\s+/)) {
      if (clause.length <= max) pieces.push(clause);
      else pieces.push(...pack(clause.split(" "), max));
    }
  }
  return pack(pieces, max);
}

/** Join consecutive pieces with spaces while they fit in `max`; a single word longer than `max` stands alone. */
function pack(pieces: string[], max: number): string[] {
  const chunks: string[] = [];
  let chunk = "";
  for (const piece of pieces) {
    if (!piece) continue;
    if (chunk && chunk.length + 1 + piece.length > max) {
      chunks.push(chunk);
      chunk = piece;
    } else {
      chunk = chunk ? `${chunk} ${piece}` : piece;
    }
  }
  if (chunk) chunks.push(chunk);
  return chunks;
}

function browserSpeech(): SpeechDeps | null {
  if (typeof window === "undefined" || !window.speechSynthesis || typeof SpeechSynthesisUtterance === "undefined") {
    return null;
  }
  const synth = window.speechSynthesis;
  return {
    // The DOM's handler and voice types are stricter than the structural ones here; the shapes match.
    synth: synth as unknown as SynthLike,
    makeUtterance: (text) => new SpeechSynthesisUtterance(text) as unknown as UtteranceLike,
  };
}
