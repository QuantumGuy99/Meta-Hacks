// The interviewer's voice: browser text to speech with speechSynthesis (PLAN §14.7). Meta has no TTS model and
// third-party TTS is ruled out, so this is the only voice out, and it should sound as human as the browser
// allows: the most natural English voice installed (or the one the candidate picked), a slightly brisk rate, and
// one utterance per sentence, so the first sentence starts at once and nothing breaks mid-phrase (Chrome also
// cuts an utterance off after about 15 s). onStart/onEnd drive the speaking indicator and the mic's silence
// (§8.3), cancel() is the barge-in.
// Keep this file free of TypeScript-only runtime syntax (enums, namespaces) so Node can run its tests with type
// stripping. The browser parts sit behind `SpeechDeps`, so tests fake them; without speechSynthesis (old
// browsers, the server render) every call is a no-op.

export const RATE = 1.05;
export const PITCH = 1;
export const MAX_SENTENCE_CHARS = 220; // only a sentence longer than this (about 14 s) is split, at its clauses
export const VOICES_WAIT_MS = 1_500; // some browsers never fire voiceschanged: speak in the default voice after this
export const STALL_CHECK_MS = 1_000; // how often to look for a chunk whose end event never came
export const VOICE_KEY = "ares.voice"; // the candidate's voice pick, per browser

/** Novelty voices (sound effects, singing) and the Eloquence voices (Eddy, Flo, Reed…): never picked or listed. */
const NEVER_VOICES =
  /^(albert|bad news|bahh|bells|boing|bubbles|cellos|deranged|fred|good news|hysterical|jester|junior|kathy|organ|pipe organ|ralph|superstar|trinoids|whisper|wobble|zarvox|eddy|flo|grandma|grandpa|reed|rocko|sandy|shelley)\b/i;

/** Voice tiers, most human first. Within a tier, en-US comes before the other English voices. */
const VOICE_TIERS: RegExp[] = [
  /\b(ava|andrew|emma|brian)\w* online \(natural\)/i, // Edge's newest neural voices
  /online \(natural\)/i, // Edge's other neural voices
  /\(premium\)/i, // macOS downloadable voices
  /\(enhanced\)/i,
  /\b(natural|neural)\b/i,
  /^google us english$/i,
  /^google uk english female$/i,
  /^google\b/i,
  /^samantha\b/i,
  /^daniel\b/i,
  /^karen\b/i,
  /^moira\b/i,
];
const NATURAL_TIERS = 5; // the tiers above Google's voices

export interface Tts {
  /** False when the browser has no speechSynthesis: every call is then a no-op. */
  readonly supported: boolean;
  /** Between onStart and onEnd. */
  readonly speaking: boolean;
  /** The browser refused to speak before the user interacted with the page; `unlock()` from a click fixes it. */
  readonly blocked: boolean;
  /** The English voices, most human first (novelty and Eloquence voices left out). Empty until they load. */
  readonly voices: VoiceLike[];
  /** The voice in use: the candidate's pick if it's installed, else the first of `voices`. */
  readonly voice: VoiceLike | null;
  /** Queue `text` after anything still being said. Markdown is read as plain text and code blocks are skipped. */
  speak(text: string): void;
  /** Stop now and drop the queue (barge-in, skipping, leaving the room). onEnd fires if speech was playing. */
  cancel(): void;
  /** Muting stops the current speech, and `speak()` does nothing until it's unmuted. */
  setMuted(muted: boolean): void;
  /** Use this voice from the next sentence on; null goes back to the best installed one. */
  setVoice(name: string | null): void;
  /** Wake the speech engine with a silent utterance, so the first line doesn't lag. Call it from a click. */
  warm(): void;
  /** Call from a click: speaks what was blocked (or nothing) while the browser allows it. */
  unlock(): void;
  dispose(): void;
}

export interface TtsOptions {
  onStart?: () => void;
  onEnd?: () => void;
  onBlocked?: (blocked: boolean) => void;
  /** The voice list or the voice in use changed (they load late in Chrome). */
  onVoices?: (voices: VoiceLike[], voice: VoiceLike | null) => void;
  /** The candidate's saved pick (`loadVoiceChoice()`), used when that voice is installed. */
  voiceName?: string | null;
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
}

export interface UtteranceLike {
  text: string;
  lang: string;
  voice: VoiceLike | null;
  rate: number;
  pitch: number;
  volume: number;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
}

/** Where the voice pick is kept (localStorage in the browser). */
export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

const NO_TTS: Tts = {
  supported: false,
  speaking: false,
  blocked: false,
  voices: [],
  voice: null,
  speak() {},
  cancel() {},
  setMuted() {},
  setVoice() {},
  warm() {},
  unlock() {},
  dispose() {},
};

export function createTts(opts: TtsOptions = {}, deps: SpeechDeps | null = browserSpeech()): Tts {
  if (!deps) return NO_TTS;
  const { synth, makeUtterance } = deps;
  let voices: VoiceLike[] = [];
  let voiceName = opts.voiceName ?? null;
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
  const chooseVoice = () => {
    voice = voices.find((v) => v.name === voiceName) ?? voices[0] ?? null;
    opts.onVoices?.(voices, voice);
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
    u.rate = opts.rate ?? RATE;
    u.pitch = PITCH;
    u.volume = 1;
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
    voices = rankVoices(list); // re-ranked on every change: Chrome adds its network voices after the local ones
    chooseVoice();
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

  // An empty utterance: it can't be heard, but it starts the browser's speech engine.
  const silent = () => {
    const u = makeUtterance("");
    u.voice = voice;
    u.lang = voice?.lang ?? "en-US";
    u.volume = 0;
    synth.speak(u);
  };

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
    get voices() {
      return voices;
    },
    get voice() {
      return voice;
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
    setVoice(name) {
      voiceName = name;
      chooseVoice();
    },
    warm() {
      if (!disposed && !muted && !current && !synth.speaking && !synth.pending) silent();
    },
    unlock() {
      if (disposed || muted) return;
      if (queue.length && !current) pump();
      // Nothing held: a silent utterance inside the click still unlocks speech for later messages.
      else if (!current) silent();
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

/** The English voices, most human first: Edge's neural voices, macOS Premium then Enhanced voices, any other
 * natural or neural voice, Google's, then Samantha, Daniel, Karen and Moira, then the rest. Within a tier, en-US
 * comes first. Novelty and Eloquence voices are left out. */
export function rankVoices(voices: VoiceLike[]): VoiceLike[] {
  const rank = (v: VoiceLike) => {
    const tier = VOICE_TIERS.findIndex((pattern) => pattern.test(v.name));
    return (tier === -1 ? VOICE_TIERS.length : tier) * 2 + (/^en[-_]us$/i.test(v.lang) ? 0 : 1);
  };
  return voices
    .filter((v) => /^en([-_]|$)/i.test(v.lang) && !NEVER_VOICES.test(v.name))
    .map((v, i) => ({ v, r: rank(v), i }))
    .sort((a, b) => a.r - b.r || a.i - b.i)
    .map(({ v }) => v);
}

/** The best English voice, or null when there's none (the browser's default then speaks, in en-US). */
export function pickVoice(voices: VoiceLike[]): VoiceLike | null {
  return rankVoices(voices)[0] ?? null;
}

/** Edge's neural voices, macOS Premium/Enhanced voices and other natural or neural voices: the room suggests
 * installing one when the best voice is Google's or older. */
export function isNaturalVoice(voice: VoiceLike): boolean {
  return VOICE_TIERS.slice(0, NATURAL_TIERS).some((pattern) => pattern.test(voice.name));
}

/** A short name for the voice picker: "Ava (Natural) · US", "Google UK English Female". */
export function voiceLabel(voice: VoiceLike): string {
  const name = voice.name
    .replace(/^microsoft\s+/i, "")
    .replace(/\s+online\s+\(natural\)/i, " (Natural)")
    .replace(/\s+-\s+english\b.*$/i, "")
    .trim();
  const region = (voice.lang.split(/[-_]/)[1] ?? "").toUpperCase();
  const place = region === "GB" ? "UK" : region;
  return !place || new RegExp(`\\b${place}\\b`).test(name) ? name : `${name} · ${place}`;
}

/** The candidate's saved voice pick, or null for the best installed voice. Storage errors read as no pick. */
export function loadVoiceChoice(storage: StorageLike | null = browserStorage()): string | null {
  try {
    return storage?.getItem(VOICE_KEY) || null;
  } catch {
    return null;
  }
}

/** Remember the voice pick in this browser; null forgets it. A full or blocked storage is ignored. */
export function saveVoiceChoice(name: string | null, storage: StorageLike | null = browserStorage()): void {
  try {
    if (name) storage?.setItem(VOICE_KEY, name);
    else storage?.removeItem(VOICE_KEY);
  } catch {
    // private mode or storage disabled: the pick lasts for this page only
  }
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

// A full stop after these, or before a lowercase word, doesn't end the sentence.
const ABBREVIATION = /\b(e\.g|i\.e|etc|vs|mr|mrs|ms|dr|approx|incl|resp)\.$/i;

/** `text` as one chunk per sentence. Only a sentence over `max` characters is split, at commas, semicolons and
 * colons (then at spaces, if a clause alone is still too long). */
export function splitSpeech(text: string, max = MAX_SENTENCE_CHARS): string[] {
  const clean = speakable(text);
  if (!clean) return [];
  const sentences: string[] = [];
  for (const piece of clean.split(/(?<=[.!?]["')\]]?)\s+/)) {
    const last = sentences.length - 1;
    if (last >= 0 && (ABBREVIATION.test(sentences[last]) || /^[a-z]/.test(piece))) sentences[last] += ` ${piece}`;
    else sentences.push(piece);
  }
  const chunks: string[] = [];
  for (const sentence of sentences) {
    if (sentence.length <= max) {
      chunks.push(sentence);
      continue;
    }
    const clauses = sentence.split(/(?<=[,;:])\s+/).flatMap((c) => (c.length <= max ? [c] : pack(c.split(" "), max)));
    chunks.push(...pack(clauses, max));
  }
  return chunks;
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

function browserStorage(): StorageLike | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null; // a sandboxed page can throw on the localStorage getter itself
  }
}
