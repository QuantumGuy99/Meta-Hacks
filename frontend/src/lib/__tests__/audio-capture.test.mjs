// Tests for lib/capture/audio (PLAN §8.3, §14.3) with a fake microphone, audio graph and socket.
// Run: node --experimental-strip-types --test "frontend/src/lib/**/*.test.mjs"
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  encodeFrame,
  FRAME_SAMPLES,
  Framer,
  Resampler,
  STOP_CLOSE_MS,
  startAudioCapture,
} from "../capture/audio/index.ts";

class FakeSocket {
  binaryType = "blob";
  readyState = 0;
  onopen = null;
  onclose = null;
  onerror = null;
  sent = [];
  closedWith = null;

  send(data) {
    this.sent.push(data);
  }
  close(code) {
    this.closedWith = code;
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  serverClose(code) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
  texts() {
    return this.sent.filter((d) => typeof d === "string").map((d) => JSON.parse(d));
  }
  frames() {
    return this.sent.filter((d) => d instanceof ArrayBuffer);
  }
}

function fakes({ micError = null, rate = 48_000 } = {}) {
  const socket = new FakeSocket();
  const tracks = [{ stopped: false, stop() { this.stopped = true; } }];
  let feed = null;
  const deps = {
    async getUserMedia() {
      if (micError) throw micError;
      return { getTracks: () => tracks };
    },
    async openGraph(_stream, onSamples) {
      feed = (seconds, value = 0.25) => onSamples(new Float32Array(Math.round(seconds * rate)).fill(value), rate);
      return { closed: false, close() { this.closed = true; } };
    },
    openSocket: () => socket,
  };
  return { deps, socket, tracks, speak: (seconds, value) => feed(seconds, value) };
}

// --- PCM ---------------------------------------------------------------------------------------------------

test("48 kHz halves to 24 kHz, averaging each pair", () => {
  const out = new Resampler(48_000).push(new Float32Array([0, 1, 1, 1, 0.5, -0.5]));
  assert.deepEqual([...out], [0.5, 1, 0]);
});

test("44.1 kHz gives 24,000 samples a second, across many blocks", () => {
  const resampler = new Resampler(44_100);
  let total = 0;
  for (let i = 0; i < 100; i++) total += resampler.push(new Float32Array(441)).length;
  assert.ok(Math.abs(total - 24_000) <= 1, `got ${total}`);
});

test("frames are 1,920 samples, scaled and clamped to 16 bits", () => {
  const framer = new Framer();
  const frames = framer.push(new Float32Array(4_000).fill(2)); // over-range clamps to 1
  assert.equal(frames.length, 2);
  assert.equal(frames[0].length, FRAME_SAMPLES);
  assert.equal(frames[0][0], 32_767);
  assert.equal(framer.push(new Float32Array(FRAME_SAMPLES - 160).fill(-1))[0][FRAME_SAMPLES - 1], -32_768);
});

test("frames are little-endian bytes", () => {
  const bytes = new Uint8Array(encodeFrame(new Int16Array([1, -2])));
  assert.deepEqual([...bytes], [1, 0, 0xfe, 0xff]);
});

// --- startAudioCapture -----------------------------------------------------------------------------------------

test("sends start, then 3,840-byte frames at real-time pace", async () => {
  const { deps, socket, speak } = fakes();
  const states = [];
  await startAudioCapture({ wsUrl: "ws://x/audio", onState: (s) => states.push(s) }, deps);
  speak(0.2); // before the socket opens: dropped, never queued
  socket.open();
  speak(0.48); // 480 ms → 6 frames
  assert.deepEqual(socket.texts(), [{ type: "start" }]);
  assert.equal(socket.frames().length, 6);
  assert.ok(socket.frames().every((f) => f.byteLength === 3_840));
  assert.deepEqual(states, ["starting", "live"]);
  assert.equal(socket.binaryType, "arraybuffer");
});

test("paused sends silence instead of the mic, so the pace holds", async () => {
  const { deps, socket, speak } = fakes();
  const capture = await startAudioCapture({ wsUrl: "ws://x/audio" }, deps);
  socket.open();
  capture.setPaused(true);
  speak(0.16, 0.5);
  capture.setPaused(false);
  speak(0.16, 0.5);
  const [silent, , loud] = socket.frames().map((f) => new Int16Array(f));
  assert.ok(silent.every((x) => x === 0));
  assert.ok(loud.every((x) => x > 0));
});

test("the Ask button sends ask frames", async () => {
  const { deps, socket } = fakes();
  const capture = await startAudioCapture({ wsUrl: "ws://x/audio" }, deps);
  socket.open();
  capture.setAsking(true);
  capture.setAsking(false);
  assert.deepEqual(socket.texts().slice(1), [
    { type: "ask", holding: true },
    { type: "ask", holding: false },
  ]);
});

test("stop sends stop, releases the mic and closes after the server's grace period", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { deps, socket, tracks, speak } = fakes();
  const states = [];
  const capture = await startAudioCapture({ wsUrl: "ws://x/audio", onState: (s) => states.push(s) }, deps);
  socket.open();
  capture.stop();
  speak(0.16); // nothing after stop
  assert.deepEqual(socket.texts().at(-1), { type: "stop" });
  assert.equal(socket.frames().length, 0);
  assert.ok(tracks[0].stopped);
  assert.equal(socket.closedWith, null);
  t.mock.timers.tick(STOP_CLOSE_MS);
  assert.equal(socket.closedWith, 1000);
  assert.deepEqual(states, ["starting", "live", "stopped"]);
});

test("the server refusing voice is an error state, and the mic is released", async () => {
  const { deps, socket, tracks } = fakes();
  const states = [];
  await startAudioCapture({ wsUrl: "ws://x/audio", onState: (s) => states.push(s) }, deps);
  socket.open();
  socket.serverClose(4503);
  assert.equal(states.at(-1), "error");
  assert.ok(tracks[0].stopped);
});

test("a denied microphone reports an error and rejects", async () => {
  const { deps } = fakes({ micError: new Error("NotAllowedError") });
  const states = [];
  await assert.rejects(startAudioCapture({ wsUrl: "ws://x/audio", onState: (s) => states.push(s) }, deps));
  assert.deepEqual(states, ["starting", "error"]);
});
