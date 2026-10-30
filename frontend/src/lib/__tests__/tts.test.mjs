// Tests for lib/tts.ts (PLAN §14.7) with a fake speechSynthesis.
// Run: node --experimental-strip-types --test "frontend/src/lib/**/*.test.mjs"
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  createTts,
  isNaturalVoice,
  loadVoiceChoice,
  MAX_SENTENCE_CHARS,
  pickVoice,
  rankVoices,
  saveVoiceChoice,
  SETTLE_MS,
  speakable,
  splitSpeech,
  STALL_CHECK_MS,
  START_TIMEOUT_MS,
  VOICE_KEY,
  voiceLabel,
  VOICES_WAIT_MS,
} from "../tts.ts";

const voice = (name, lang = "en-US") => ({ name, lang });
const VOICES = [voice("Alex"), voice("Google US English"), voice("Samantha"), voice("Thomas", "fr-FR")];

// The English voices Chrome 156 lists on our Mac (Oct 28), in Chrome's order: no Natural, Premium or Enhanced ones.
const CHROME_MAC = [
  ["Samantha", "en-US"], ["Albert", "en-US"], ["Bad News", "en-US"], ["Bahh", "en-US"], ["Bells", "en-US"],
  ["Boing", "en-US"], ["Bubbles", "en-US"], ["Cellos", "en-US"], ["Daniel", "en-GB"],
  ["Eddy (English (United States))", "en-US"], ["Eddy (English (United Kingdom))", "en-GB"],
  ["Flo (English (United States))", "en-US"], ["Flo (English (United Kingdom))", "en-GB"], ["Fred", "en-US"],
  ["Good News", "en-US"], ["Grandma (English (United States))", "en-US"], ["Grandma (English (United Kingdom))", "en-GB"],
  ["Grandpa (English (United States))", "en-US"], ["Grandpa (English (United Kingdom))", "en-GB"], ["Jester", "en-US"],
  ["Junior", "en-US"], ["Karen", "en-AU"], ["Kathy", "en-US"], ["Moira", "en-IE"], ["Organ", "en-US"], ["Ralph", "en-US"],
  ["Reed (English (United States))", "en-US"], ["Reed (English (United Kingdom))", "en-GB"], ["Rishi", "en-IN"],
  ["Rocko (English (United States))", "en-US"], ["Rocko (English (United Kingdom))", "en-GB"],
  ["Sandy (English (United States))", "en-US"], ["Sandy (English (United Kingdom))", "en-GB"],
  ["Shelley (English (United States))", "en-US"], ["Shelley (English (United Kingdom))", "en-GB"], ["Superstar", "en-US"],
  ["Tessa", "en-ZA"], ["Trinoids", "en-US"], ["Whisper", "en-US"], ["Wobble", "en-US"], ["Zarvox", "en-US"],
  ["Google US English", "en-US"], ["Google UK English Female", "en-GB"], ["Google UK English Male", "en-GB"],
  ["Amélie", "fr-CA"],
].map(([name, lang]) => voice(name, lang));

// Speaks one utterance at a time, like the browser; the test drives start, end and errors.
class FakeSynth {
  voices = [];
  listeners = new Set();
  spoken = [];
  current = null;
  speaking = false;
  pending = false;
  paused = false;
  cancels = 0;

  getVoices() {
    return this.voices;
  }
  addEventListener(type, listener) {
    if (type === "voiceschanged") this.listeners.add(listener);
  }
  removeEventListener(type, listener) {
    this.listeners.delete(listener);
  }
  loadVoices(voices) {
    this.voices = voices;
    for (const listener of this.listeners) listener();
  }
  speak(u) {
    this.spoken.push(u);
    if (!u.onstart) return; // a silent warm-up or unlock utterance
    this.current = u;
    this.pending = true;
  }
  cancel() {
    this.cancels += 1;
    const u = this.current;
    this.current = null;
    this.speaking = false;
    this.pending = false;
    u?.onerror?.({ error: "interrupted" });
  }
  resume() {
    this.paused = false;
  }
  // test controls
  start() {
    this.pending = false;
    this.speaking = true;
    this.current.onstart();
  }
  end() {
    const u = this.current;
    this.current = null;
    this.speaking = false;
    u.onend();
  }
  fail(error) {
    const u = this.current;
    this.current = null;
    this.speaking = false;
    this.pending = false;
    u.onerror({ error });
  }
  /** Start and finish every utterance until the queue is empty. */
  finishAll() {
    while (this.current) {
      this.start();
      this.end();
    }
  }
  texts() {
    return this.spoken.map((u) => u.text);
  }
}

const makeUtterance = (text) => ({
  text,
  lang: "",
  voice: null,
  rate: 1,
  pitch: 1,
  volume: 1,
  onstart: null,
  onend: null,
  onerror: null,
});

function setup({ voices = VOICES, ...opts } = {}) {
  const synth = new FakeSynth();
  synth.voices = voices;
  const events = [];
  const tts = createTts(
    {
      onStart: () => events.push("start"),
      onEnd: () => events.push("end"),
      onBlocked: (b) => events.push(b ? "blocked" : "unblocked"),
      ...opts,
    },
    { synth, makeUtterance },
  );
  return { synth, tts, events };
}

class FakeStorage {
  items = new Map();
  getItem(key) {
    return this.items.get(key) ?? null;
  }
  setItem(key, value) {
    this.items.set(key, value);
  }
  removeItem(key) {
    this.items.delete(key);
  }
}

// --- voice ranking -------------------------------------------------------------------------------------------

test("ranks Edge's neural voices, then Premium, Enhanced, other natural, Google, then the old macOS voices", () => {
  const all = [
    voice("Moira", "en-IE"),
    voice("Karen", "en-AU"),
    voice("Daniel", "en-GB"),
    voice("Samantha"),
    voice("Google UK English Male", "en-GB"),
    voice("Google UK English Female", "en-GB"),
    voice("Google US English"),
    voice("Some Neural Voice"),
    voice("Evan (Enhanced)"),
    voice("Zoe (Premium)"),
    voice("Microsoft Aria Online (Natural) - English (United States)"),
    voice("Microsoft Ava Online (Natural) - English (United States)"),
    voice("Rishi", "en-IN"),
  ];
  assert.deepEqual(
    rankVoices(all).map((v) => v.name),
    [
      "Microsoft Ava Online (Natural) - English (United States)",
      "Microsoft Aria Online (Natural) - English (United States)",
      "Zoe (Premium)",
      "Evan (Enhanced)",
      "Some Neural Voice",
      "Google US English",
      "Google UK English Female",
      "Google UK English Male",
      "Samantha",
      "Daniel",
      "Karen",
      "Moira",
      "Rishi",
    ],
  );
});

test("within a tier, en-US comes before the other English voices", () => {
  assert.equal(pickVoice([voice("Serena (Premium)", "en-GB"), voice("Ava (Premium)")]).name, "Ava (Premium)");
  assert.equal(pickVoice([voice("Libby (Natural)", "en-GB"), voice("Jenny (Natural)")]).name, "Jenny (Natural)");
  assert.equal(pickVoice([voice("Tessa", "en-ZA"), voice("Alex")]).name, "Alex");
  assert.equal(pickVoice([voice("Daniel", "en_GB")]).name, "Daniel");
});

test("Edge's multilingual neural voices count as its newest ones", () => {
  const edge = [
    voice("Microsoft Guy Online (Natural) - English (United States)"),
    voice("Microsoft AndrewMultilingual Online (Natural) - English (United States)"),
  ];
  assert.match(pickVoice(edge).name, /AndrewMultilingual/);
});

test("on our Mac's Chrome: Google US English, and no novelty or Eloquence voice is ever listed", () => {
  const ranked = rankVoices(CHROME_MAC).map((v) => v.name);
  assert.equal(pickVoice(CHROME_MAC).name, "Google US English");
  assert.deepEqual(ranked, [
    "Google US English",
    "Google UK English Female",
    "Google UK English Male",
    "Samantha",
    "Daniel",
    "Karen",
    "Moira",
    "Rishi",
    "Tessa",
  ]);
});

test("a list of only novelty, Eloquence and non-English voices has no pick", () => {
  const junk = ["Albert", "Bad News", "Zarvox", "Whisper", "Fred", "Kathy", "Eddy (English (United States))",
    "Flo (English (United Kingdom))", "Grandma (English (United States))", "Reed (English (United States))",
    "Rocko (English (United States))", "Sandy (English (United States))", "Shelley (English (United States))"];
  assert.deepEqual(rankVoices(junk.map((n) => voice(n))), []);
  assert.equal(pickVoice([...junk.map((n) => voice(n)), voice("Amélie (Natural)", "fr-CA")]), null);
  assert.equal(pickVoice([]), null);
});

test("natural voices are Edge's neural, Premium, Enhanced and other natural ones; Google's and Samantha aren't", () => {
  assert.ok(isNaturalVoice(voice("Microsoft Emma Online (Natural) - English (United States)")));
  assert.ok(isNaturalVoice(voice("Ava (Premium)")));
  assert.ok(isNaturalVoice(voice("Evan (Enhanced)")));
  assert.equal(isNaturalVoice(voice("Google US English")), false);
  assert.equal(isNaturalVoice(voice("Samantha")), false);
});

test("picker labels are short", () => {
  assert.equal(voiceLabel(voice("Microsoft Ava Online (Natural) - English (United States)")), "Ava (Natural) · US");
  assert.equal(voiceLabel(voice("Zoe (Premium)")), "Zoe (Premium) · US");
  assert.equal(voiceLabel(voice("Google US English")), "Google US English");
  assert.equal(voiceLabel(voice("Google UK English Female", "en-GB")), "Google UK English Female");
  assert.equal(voiceLabel(voice("Daniel", "en-GB")), "Daniel · UK");
  assert.equal(voiceLabel(voice("Moira", "en-IE")), "Moira · IE");
});

// --- the saved pick ------------------------------------------------------------------------------------------

test("a saved pick is used when it's installed, even over a better voice", () => {
  const { synth, tts } = setup({ voiceName: "Samantha" });
  assert.equal(tts.voice.name, "Samantha");
  tts.speak("Hello.");
  assert.equal(synth.spoken[0].voice.name, "Samantha");
});

test("a saved pick that isn't installed falls back to the best voice", () => {
  const { tts } = setup({ voiceName: "Ava (Premium)" });
  assert.equal(tts.voice.name, "Google US English");
});

test("a saved pick applies once the voices load, and onVoices reports the list and the voice", () => {
  const seen = [];
  const { synth, tts } = setup({ voices: [], voiceName: "Samantha", onVoices: (list, v) => seen.push([list.length, v?.name]) });
  assert.equal(tts.voice, null);
  synth.loadVoices(VOICES);
  assert.deepEqual(seen, [[3, "Samantha"]]);
  assert.deepEqual(tts.voices.map((v) => v.name), ["Google US English", "Samantha", "Alex"]);
});

test("setVoice switches from the next sentence, and null goes back to the best", () => {
  const { synth, tts } = setup();
  tts.speak("One. Two.");
  synth.start();
  tts.setVoice("Samantha");
  synth.end();
  assert.equal(synth.spoken[0].voice.name, "Google US English");
  assert.equal(synth.spoken[1].voice.name, "Samantha");
  tts.setVoice(null);
  assert.equal(tts.voice.name, "Google US English");
});

test("the pick is saved per browser, and storage errors are harmless", () => {
  const storage = new FakeStorage();
  assert.equal(loadVoiceChoice(storage), null);
  saveVoiceChoice("Samantha", storage);
  assert.equal(storage.getItem(VOICE_KEY), "Samantha");
  assert.equal(loadVoiceChoice(storage), "Samantha");
  saveVoiceChoice(null, storage);
  assert.equal(loadVoiceChoice(storage), null);
  const broken = { getItem() { throw new Error("denied"); }, setItem() { throw new Error("full"); }, removeItem() {} };
  assert.equal(loadVoiceChoice(broken), null);
  saveVoiceChoice("Samantha", broken);
  assert.equal(loadVoiceChoice(null), null); // no storage at all (Node, the server render)
});

// --- text and prosody ----------------------------------------------------------------------------------------

test("markdown is read as plain text and code blocks are skipped", () => {
  assert.equal(
    speakable("## Plan\n**Nice.** Use a `hash_map` and see [the docs](https://x.y).\n```python\nx = 1\n```\n- done"),
    "Plan Nice. Use a hash map and see the docs. done",
  );
});

test("one chunk per sentence; numbers, abbreviations and lowercase run-ons don't split", () => {
  assert.deepEqual(splitSpeech("It takes 3.5 seconds. Why? Because!"), ["It takes 3.5 seconds.", "Why?", "Because!"]);
  assert.deepEqual(splitSpeech("Try a heap, e.g. a min-heap. Then sort it, i.e. in place."), [
    "Try a heap, e.g. a min-heap.",
    "Then sort it, i.e. in place.",
  ]);
  assert.deepEqual(splitSpeech("Use O(n). then check it."), ["Use O(n). then check it."]);
  assert.deepEqual(splitSpeech("   "), []);
});

test("only a sentence over the limit splits, at its clauses, never over the limit", () => {
  const long = `Then ${"word ".repeat(30).trim()}, and then ${"more ".repeat(30).trim()}; finally ${"done ".repeat(20).trim()}.`;
  const chunks = splitSpeech(`Short one. ${long}`);
  assert.equal(chunks[0], "Short one.");
  assert.ok(chunks.length >= 3);
  assert.ok(chunks.every((c) => c.length <= MAX_SENTENCE_CHARS), chunks.map((c) => c.length).join(","));
  assert.ok(chunks.slice(1, -1).every((c) => /[,;]$/.test(c)), "each piece ends at a clause");
  assert.equal(chunks.slice(1).join(" "), long);
});

test("speaks at a slightly brisk rate and natural pitch, the first sentence on its own", () => {
  const { synth, tts } = setup();
  tts.speak("Hi, I'm your interviewer. Your problem is on the left, so take a moment to read it.");
  const [u] = synth.spoken;
  assert.equal(u.text, "Hi, I'm your interviewer.");
  assert.equal(u.rate, 1.05);
  assert.equal(u.pitch, 1);
  assert.equal(u.volume, 1);
});

test("warm() speaks one silent, empty utterance in the default voice when idle, and not while busy or muted", () => {
  const { synth, tts } = setup();
  tts.warm();
  assert.deepEqual(synth.texts(), [""]);
  assert.equal(synth.spoken[0].volume, 0);
  assert.equal(synth.spoken[0].voice, null); // a network voice like Google's doesn't warm up
  tts.speak("Hello.");
  tts.warm();
  tts.setMuted(true);
  tts.warm();
  assert.deepEqual(synth.texts(), ["", "Hello."]);
});

test("warm() right after a cancel does nothing, even from a new Tts (the room's remount)", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const synth = new FakeSynth();
  synth.voices = VOICES;
  const deps = { synth, makeUtterance };
  const first = createTts({}, deps);
  first.speak("Hello.");
  first.dispose(); // cancels
  const second = createTts({}, deps);
  second.warm();
  assert.deepEqual(synth.texts(), ["Hello."]);
  t.mock.timers.tick(SETTLE_MS);
  second.warm();
  assert.deepEqual(synth.texts(), ["Hello.", ""]);
});

// --- the queue -----------------------------------------------------------------------------------------------

test("speaks chunks one at a time; onStart once at the first, onEnd once after the last", () => {
  const { synth, tts, events } = setup();
  const first = "A".repeat(175) + ".";
  tts.speak(`${first} Second sentence.`);
  tts.speak("Another message.");
  assert.equal(synth.spoken.length, 1);
  assert.equal(synth.spoken[0].voice.name, "Google US English");
  assert.equal(synth.spoken[0].lang, "en-US");
  synth.start();
  assert.ok(tts.speaking);
  synth.end();
  synth.finishAll();
  assert.deepEqual(synth.texts(), [first, "Second sentence.", "Another message."]); // messages aren't merged
  assert.deepEqual(events, ["start", "end"]);
  assert.equal(tts.speaking, false);
});

test("waits for voiceschanged before speaking, then uses the preferred voice", () => {
  const { synth, tts } = setup({ voices: [] });
  tts.speak("Hello.");
  assert.equal(synth.spoken.length, 0);
  synth.loadVoices(VOICES);
  assert.equal(synth.spoken.length, 1);
  assert.equal(synth.spoken[0].voice.name, "Google US English");
});

test("speaks in the default voice if voiceschanged never comes", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { synth, tts } = setup({ voices: [] });
  tts.speak("Hello.");
  t.mock.timers.tick(VOICES_WAIT_MS);
  assert.equal(synth.spoken.length, 1);
  assert.equal(synth.spoken[0].voice, null);
  assert.equal(synth.spoken[0].lang, "en-US");
});

test("cancel stops at once, drops the queue and ignores the late interrupted error", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const { synth, tts, events } = setup();
  tts.speak("One. ".repeat(50));
  synth.start();
  tts.cancel();
  assert.equal(synth.cancels, 1);
  assert.equal(synth.current, null);
  assert.deepEqual(events, ["start", "end"]);
  assert.equal(synth.spoken.length, 1); // the rest of the queue is gone
  tts.speak("Next.");
  assert.equal(synth.current, null); // Chrome can wedge on speak() right after cancel(): wait a moment
  t.mock.timers.tick(SETTLE_MS);
  synth.finishAll();
  assert.deepEqual(events, ["start", "end", "start", "end"]);
});

test("cancel before anything started doesn't report an end", () => {
  const { synth, tts, events } = setup();
  tts.speak("Hello.");
  tts.cancel();
  assert.deepEqual(events, []);
  assert.equal(synth.cancels, 1);
});

test("muted: stops the speech and ignores speak until unmuted", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const { synth, tts, events } = setup();
  tts.speak("Hello.");
  synth.start();
  tts.setMuted(true);
  assert.deepEqual(events, ["start", "end"]);
  tts.speak("Ignored.");
  assert.equal(synth.spoken.length, 1);
  tts.setMuted(false);
  tts.speak("Heard.");
  t.mock.timers.tick(SETTLE_MS);
  assert.deepEqual(synth.texts(), ["Hello.", "Heard."]);
});

test("a synthesis error skips that chunk and carries on", () => {
  const { synth, tts, events } = setup();
  tts.speak(`${"A".repeat(175)}. Second.`);
  synth.start();
  synth.fail("synthesis-failed");
  assert.equal(synth.current.text, "Second.");
  synth.finishAll();
  assert.deepEqual(events, ["start", "end"]);
});

// --- blocked by the browser ----------------------------------------------------------------------------------

test("not-allowed holds the newest message until unlock() from a click", () => {
  const { synth, tts, events } = setup();
  tts.speak("Welcome.");
  synth.fail("not-allowed");
  assert.ok(tts.blocked);
  assert.equal(tts.speaking, false);
  tts.speak("Here is the problem."); // replaces the held message and tries again
  synth.fail("not-allowed");
  tts.unlock();
  assert.equal(synth.current.text, "Here is the problem.");
  synth.start();
  assert.equal(tts.blocked, false);
  synth.end();
  assert.deepEqual(events, ["blocked", "unblocked", "start", "end"]);
  assert.deepEqual(synth.texts(), ["Welcome.", "Here is the problem.", "Here is the problem."]);
});

test("unlock() with nothing held speaks an empty utterance to unlock later speech", () => {
  const { synth, tts } = setup();
  tts.unlock();
  assert.deepEqual(synth.texts(), [""]);
});

test("a chunk the browser silently drops counts as blocked (Safari)", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const { synth, tts, events } = setup();
  tts.speak("Hello.");
  synth.pending = false; // never started, no error
  t.mock.timers.tick(STALL_CHECK_MS);
  assert.ok(tts.blocked);
  assert.deepEqual(events, ["blocked"]);
});

// --- Chrome's lost events ------------------------------------------------------------------------------------

test("a lost end event: once the engine is idle, the next chunk plays and onEnd still fires", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const { synth, tts, events } = setup();
  tts.speak(`${"A".repeat(175)}. Second.`);
  synth.start();
  t.mock.timers.tick(STALL_CHECK_MS); // still speaking: keep waiting
  assert.equal(synth.spoken.length, 1);
  synth.speaking = false; // finished, but onend never fired
  synth.current = null;
  t.mock.timers.tick(STALL_CHECK_MS);
  assert.equal(synth.spoken.length, 2);
  synth.finishAll();
  assert.deepEqual(events, ["start", "end"]);
});

test("a sentence stuck behind a wedged queue is cleared and retried once, then skipped", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const { synth, tts, events } = setup();
  tts.speak("Hi, I'm your interviewer. Second.");
  synth.speaking = true; // the engine says it's busy, but our sentence never starts
  t.mock.timers.tick(START_TIMEOUT_MS + STALL_CHECK_MS);
  assert.equal(synth.cancels, 1);
  t.mock.timers.tick(SETTLE_MS);
  assert.deepEqual(synth.texts(), ["Hi, I'm your interviewer.", "Hi, I'm your interviewer."]);
  synth.speaking = true; // stuck again: skip it and go on
  t.mock.timers.tick(START_TIMEOUT_MS + STALL_CHECK_MS);
  assert.equal(synth.cancels, 2);
  t.mock.timers.tick(SETTLE_MS);
  assert.equal(synth.current.text, "Second.");
  synth.finishAll();
  assert.deepEqual(events, ["start", "end"]);
  assert.equal(tts.blocked, false);
});

test("a chunk stuck far past its length is cut, so the mic isn't held silent", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const { synth, tts, events } = setup();
  tts.speak("Stuck.");
  synth.start();
  t.mock.timers.tick(10 * STALL_CHECK_MS);
  assert.equal(synth.cancels, 1);
  assert.deepEqual(events, ["start", "end"]);
});

// --- lifecycle -----------------------------------------------------------------------------------------------

test("without speechSynthesis every call is a safe no-op", () => {
  const tts = createTts({ onStart: () => assert.fail("no speech") }, null);
  assert.equal(tts.supported, false);
  tts.speak("Hello.");
  tts.setMuted(true);
  tts.unlock();
  tts.cancel();
  tts.dispose();
  assert.equal(tts.speaking, false);
});

test("in Node (no window) the default is the no-op", () => {
  assert.equal(createTts().supported, false);
});

test("dispose stops speaking and stops listening for voices", () => {
  const { synth, tts, events } = setup();
  tts.speak("Hello.");
  synth.start();
  tts.dispose();
  assert.deepEqual(events, ["start", "end"]);
  assert.equal(synth.listeners.size, 0);
  tts.speak("Ignored.");
  assert.equal(synth.spoken.length, 1);
});

test("resumes a paused engine before speaking", () => {
  const { synth, tts } = setup();
  synth.paused = true;
  tts.speak("Hello.");
  assert.equal(synth.paused, false);
});
