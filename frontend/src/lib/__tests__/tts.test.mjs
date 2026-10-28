// Tests for lib/tts.ts (PLAN §14.7) with a fake speechSynthesis.
// Run: node --experimental-strip-types --test "frontend/src/lib/**/*.test.mjs"
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  createTts,
  MAX_CHUNK_CHARS,
  pickVoice,
  speakable,
  splitSpeech,
  STALL_CHECK_MS,
  VOICES_WAIT_MS,
} from "../tts.ts";

const voice = (name, lang = "en-US", isDefault = false) => ({ name, lang, default: isDefault });
const VOICES = [voice("Alex", "en-US", true), voice("Google US English"), voice("Thomas", "fr-FR")];

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
    if (!u.onstart) return; // unlock()'s empty utterance
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
    { synth, makeUtterance: (text) => ({ text, lang: "", voice: null, rate: 1, onstart: null, onend: null, onerror: null }) },
  );
  return { synth, tts, events };
}

// --- voice and text ------------------------------------------------------------------------------------------

test("prefers a natural voice, then Google US English, then Samantha, English only", () => {
  assert.equal(pickVoice([...VOICES, voice("Microsoft Aria Online (Natural) - English (United States)")]).name,
    "Microsoft Aria Online (Natural) - English (United States)");
  assert.equal(pickVoice(VOICES).name, "Google US English");
  assert.equal(pickVoice([voice("Alex", "en-US", true), voice("Samantha")]).name, "Samantha");
  assert.equal(pickVoice([voice("Amélie (Natural)", "fr-CA"), voice("Alex", "en-US", true)]).name, "Alex");
});

test("prefers US English, then the default, then any English; none is null", () => {
  assert.equal(pickVoice([voice("Libby (Natural)", "en-GB"), voice("Jenny (Natural)", "en-US")]).name, "Jenny (Natural)");
  assert.equal(pickVoice([voice("Daniel", "en-GB"), voice("Fred", "en-US", true)]).name, "Fred");
  assert.equal(pickVoice([voice("Daniel", "en_GB")]).name, "Daniel");
  assert.equal(pickVoice([voice("Thomas", "fr-FR")]), null);
  assert.equal(pickVoice([]), null);
});

test("markdown is read as plain text and code blocks are skipped", () => {
  assert.equal(
    speakable("## Plan\n**Nice.** Use a `hash_map` and see [the docs](https://x.y).\n```python\nx = 1\n```\n- done"),
    "Plan Nice. Use a hash map and see the docs. done",
  );
});

test("sentences are packed into chunks, and numbers aren't split", () => {
  assert.deepEqual(splitSpeech("It takes 3.5 seconds. Why? Because!", 20), ["It takes 3.5", "seconds. Why?", "Because!"]);
  assert.deepEqual(splitSpeech("Hi there. How are you? Good."), ["Hi there. How are you? Good."]);
  assert.deepEqual(splitSpeech("   "), []);
});

test("a long sentence splits at commas, then at spaces, never over the limit", () => {
  const long = `${"word ".repeat(60).trim()}, and then ${"more ".repeat(40).trim()}.`;
  const chunks = splitSpeech(long);
  assert.ok(chunks.length >= 3);
  assert.ok(chunks.every((c) => c.length <= MAX_CHUNK_CHARS), chunks.map((c) => c.length).join(","));
  assert.equal(chunks.join(" "), long);
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

test("cancel stops at once, drops the queue and ignores the late interrupted error", () => {
  const { synth, tts, events } = setup();
  tts.speak("One. ".repeat(50));
  synth.start();
  tts.cancel();
  assert.equal(synth.cancels, 1);
  assert.equal(synth.current, null);
  assert.deepEqual(events, ["start", "end"]);
  assert.equal(synth.spoken.length, 1); // the rest of the queue is gone
  tts.speak("Next.");
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

test("muted: stops the speech and ignores speak until unmuted", () => {
  const { synth, tts, events } = setup();
  tts.speak("Hello.");
  synth.start();
  tts.setMuted(true);
  assert.deepEqual(events, ["start", "end"]);
  tts.speak("Ignored.");
  assert.equal(synth.spoken.length, 1);
  tts.setMuted(false);
  tts.speak("Heard.");
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
