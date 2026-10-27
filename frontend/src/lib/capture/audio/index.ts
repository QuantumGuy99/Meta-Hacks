// Microphone → 24 kHz 16-bit PCM in 80 ms frames → the session's audio socket (PLAN §8.3, §14.3).
// Keep this file free of TypeScript-only runtime syntax (enums, namespaces) so Node can run its tests with
// type stripping. The browser parts (mic, AudioWorklet, WebSocket) sit behind `AudioDeps`, so tests fake them.

export const TARGET_RATE = 24_000;
export const FRAME_SAMPLES = 1_920; // 80 ms at 24 kHz = 3,840 bytes per binary frame
export const STOP_CLOSE_MS = 6_000; // after "stop", how long the server may take to send the last turns

export type AudioState = "starting" | "live" | "error" | "stopped";

export interface AudioCapture {
  /** True while TTS speaks: the mic is replaced by silence, so the interviewer's voice isn't transcribed but
   * the stream keeps its real-time pace (Meta closes streams that fall behind). */
  setPaused(paused: boolean): void;
  /** The Ask button: what the candidate says while holding it is a question to the interviewer. */
  setAsking(holding: boolean): void;
  stop(): void;
}

export interface AudioCaptureOptions {
  wsUrl: string; // /ws/sessions/{id}/audio
  onState?: (state: AudioState) => void;
}

/** What `startAudioCapture` needs from the browser. */
export interface AudioDeps {
  getUserMedia(constraints: MediaStreamConstraints): Promise<MicStream>;
  /** Run the mic through an AudioWorklet; `onSamples` gets mono Float32 blocks and their sample rate. */
  openGraph(
    stream: MicStream,
    onSamples: (samples: Float32Array, sampleRate: number) => void,
  ): Promise<AudioGraph>;
  openSocket(url: string): AudioSocket;
}

export interface MicStream {
  getTracks(): { stop(): void }[];
}

export interface AudioGraph {
  close(): void;
}

export interface AudioSocket {
  binaryType: string;
  readyState: number;
  onopen: (() => void) | null;
  onclose: ((e: { code: number }) => void) | null;
  onerror: (() => void) | null;
  send(data: string | ArrayBuffer): void;
  close(code?: number): void;
}

const OPEN = 1;

export async function startAudioCapture(
  opts: AudioCaptureOptions,
  deps: AudioDeps = browserDeps(),
): Promise<AudioCapture> {
  const report = (state: AudioState) => opts.onState?.(state);
  report("starting");
  let mic: MicStream;
  try {
    mic = await deps.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
    });
  } catch (err) {
    report("error"); // permission denied or no microphone: the room falls back to chat
    throw err;
  }
  let paused = false;
  let finished = false;
  let graph: AudioGraph | null = null;
  const framer = new Framer();
  let resampler: Resampler | null = null;
  const socket = deps.openSocket(opts.wsUrl);
  socket.binaryType = "arraybuffer";

  const release = () => {
    graph?.close();
    for (const track of mic.getTracks()) track.stop();
  };
  const finish = (state: AudioState) => {
    if (finished) return;
    finished = true;
    release();
    report(state);
  };

  socket.onopen = () => {
    socket.send(JSON.stringify({ type: "start" }));
    report("live");
  };
  // 1000 is a normal end (we stopped, or the session ended); 4403, 4409 and 4503 mean "use chat".
  socket.onclose = (e) => finish(e.code === 1000 ? "stopped" : "error");
  socket.onerror = () => finish("error");

  try {
    graph = await deps.openGraph(mic, (block, sampleRate) => {
      if (finished) return;
      resampler ??= new Resampler(sampleRate);
      const samples = resampler.push(block);
      if (paused) samples.fill(0);
      for (const frame of framer.push(samples)) {
        // Frames before the socket opens are dropped, not queued: the server needs real-time pace.
        if (socket.readyState === OPEN) socket.send(encodeFrame(frame));
      }
    });
  } catch (err) {
    socket.close(1000);
    finish("error");
    throw err;
  }

  return {
    setPaused(next) {
      paused = next;
    },
    setAsking(holding) {
      if (socket.readyState === OPEN) socket.send(JSON.stringify({ type: "ask", holding }));
    },
    stop() {
      if (finished) return;
      if (socket.readyState === OPEN) socket.send(JSON.stringify({ type: "stop" }));
      release();
      // The server sends the last turns on the session socket; close ours once it has had time to.
      setTimeout(() => socket.close(1000), STOP_CLOSE_MS);
      finished = true;
      report("stopped");
    },
  };
}

/** Streaming downsampler to 24 kHz: each output sample is the mean of the input samples in its window (a box
 * filter, which is enough for noise-suppressed speech). */
export class Resampler {
  readonly ratio: number;
  private consumed = 0;
  private windowEnd: number;
  private sum = 0;
  private count = 0;

  constructor(inRate: number, outRate = TARGET_RATE) {
    if (inRate < outRate) throw new Error(`can't upsample ${inRate} Hz to ${outRate} Hz`);
    this.ratio = inRate / outRate;
    this.windowEnd = this.ratio;
  }

  push(input: Float32Array): Float32Array {
    const out = new Float32Array(Math.ceil(input.length / this.ratio) + 1);
    let n = 0;
    for (let i = 0; i < input.length; i++) {
      this.sum += input[i];
      this.count += 1;
      this.consumed += 1;
      if (this.consumed >= this.windowEnd) {
        out[n++] = this.sum / this.count;
        this.sum = 0;
        this.count = 0;
        this.windowEnd += this.ratio;
      }
    }
    if (this.consumed > 1_000_000) {
      // Keep the counters small so float error can't build up over a long session.
      const whole = Math.floor(this.consumed);
      this.consumed -= whole;
      this.windowEnd -= whole;
    }
    return out.subarray(0, n);
  }
}

/** Collects 24 kHz samples into 1,920-sample Int16 frames. */
export class Framer {
  private frame = new Int16Array(FRAME_SAMPLES);
  private filled = 0;

  push(samples: Float32Array): Int16Array[] {
    const frames: Int16Array[] = [];
    for (let i = 0; i < samples.length; i++) {
      const x = Math.max(-1, Math.min(1, samples[i]));
      this.frame[this.filled++] = x < 0 ? Math.round(x * 0x8000) : Math.round(x * 0x7fff);
      if (this.filled === FRAME_SAMPLES) {
        frames.push(this.frame);
        this.frame = new Int16Array(FRAME_SAMPLES);
        this.filled = 0;
      }
    }
    return frames;
  }
}

/** Signed 16-bit little-endian, whatever the platform's byte order. */
export function encodeFrame(frame: Int16Array): ArrayBuffer {
  const buffer = new ArrayBuffer(frame.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < frame.length; i++) view.setInt16(i * 2, frame[i], true);
  return buffer;
}

// Runs on the audio thread: copies the first channel out in ~2,048-sample blocks.
const WORKLET_SOURCE = `
class CrucibleCapture extends AudioWorkletProcessor {
  constructor() { super(); this.block = new Float32Array(2048); this.n = 0; }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) {
      for (let i = 0; i < channel.length; i++) {
        this.block[this.n++] = channel[i];
        if (this.n === this.block.length) {
          this.port.postMessage(this.block, [this.block.buffer]);
          this.block = new Float32Array(2048);
          this.n = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor("crucible-capture", CrucibleCapture);
`;

function browserDeps(): AudioDeps {
  return {
    getUserMedia: (constraints) => navigator.mediaDevices.getUserMedia(constraints),
    async openGraph(stream, onSamples) {
      const context = new AudioContext();
      const url = URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: "text/javascript" }));
      try {
        await context.audioWorklet.addModule(url);
      } finally {
        URL.revokeObjectURL(url);
      }
      const source = context.createMediaStreamSource(stream as MediaStream);
      const node = new AudioWorkletNode(context, "crucible-capture");
      node.port.onmessage = (e: MessageEvent<Float32Array>) => onSamples(e.data, context.sampleRate);
      // A muted path to the speakers keeps the graph pulling audio in every browser, without playing it.
      const mute = context.createGain();
      mute.gain.value = 0;
      source.connect(node);
      node.connect(mute);
      mute.connect(context.destination);
      await context.resume();
      return {
        close() {
          source.disconnect();
          node.disconnect();
          void context.close();
        },
      };
    },
    // The DOM's handler types are stricter than AudioSocket's structural ones; the shapes match.
    openSocket: (url) => new WebSocket(url) as unknown as AudioSocket,
  };
}
