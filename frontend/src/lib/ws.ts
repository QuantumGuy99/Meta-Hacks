import type { ClientMessage, ServerMessage } from "@/types/contracts";
import { WS_URL } from "./api";

// The session WebSocket (PLAN §8.2): JSON both ways. It says `hello` on every (re)connect so the server
// replies with the current session.state, reconnects with backoff, and queues what the room sends while the
// connection is down (the capture lib's next snapshot covers anything that doesn't fit the queue).
// A `hello` every 25 s doubles as a keepalive: the server answers each one, so a connection that has gone
// quiet for a minute is treated as dead and replaced, and the timer resyncs on every answer.

export type SocketStatus = "connecting" | "open" | "reconnecting" | "closed" | "not_found";

export type SessionSocket = { send: (msg: ClientMessage) => void; close: () => void };

const NOT_FOUND_CLOSE = 4404;
const BACKOFF_MS = [500, 1000, 2000, 4000, 8000];
const MAX_QUEUED = 500;
const KEEPALIVE_MS = 25_000;
const SILENT_LIMIT_MS = 60_000;

export function connectSession(
  id: string,
  handlers: {
    onMessage: (msg: ServerMessage) => void;
    onStatus: (status: SocketStatus) => void;
    /** Called on every open; `reconnected` is true after a drop, when the room may have missed messages. */
    onOpen?: (reconnected: boolean) => void;
  },
): SessionSocket {
  let ws: WebSocket | null = null;
  let attempt = 0;
  let opened = false;
  let closed = false;
  let retry: ReturnType<typeof setTimeout> | undefined;
  let keepalive: ReturnType<typeof setInterval> | undefined;
  let lastHeard = 0;
  const queue: string[] = [];

  const hello = (socket: WebSocket) =>
    socket.send(JSON.stringify({ type: "hello", client_now_ms: Date.now() } satisfies ClientMessage));

  const scheduleRetry = () => {
    clearTimeout(retry);
    retry = setTimeout(open, BACKOFF_MS[Math.min(attempt++, BACKOFF_MS.length - 1)]);
  };

  const open = () => {
    clearTimeout(retry);
    handlers.onStatus(opened ? "reconnecting" : "connecting");
    const socket = new WebSocket(`${WS_URL}/ws/sessions/${encodeURIComponent(id)}`);
    ws = socket;
    socket.onopen = () => {
      attempt = 0;
      lastHeard = Date.now();
      handlers.onStatus("open");
      hello(socket);
      while (queue.length && socket.readyState === WebSocket.OPEN) socket.send(queue.shift()!);
      handlers.onOpen?.(opened);
      opened = true;
      clearInterval(keepalive);
      keepalive = setInterval(() => {
        if (socket.readyState !== WebSocket.OPEN) return;
        if (Date.now() - lastHeard > SILENT_LIMIT_MS) {
          socket.close(4000, "no reply to keepalive"); // onclose reconnects
          return;
        }
        hello(socket);
      }, KEEPALIVE_MS);
    };
    socket.onmessage = (e) => {
      lastHeard = Date.now();
      try {
        handlers.onMessage(JSON.parse(String(e.data)) as ServerMessage);
      } catch {
        // not JSON: ignore it rather than break the room
      }
    };
    socket.onclose = (e) => {
      if (ws === socket) ws = null;
      clearInterval(keepalive);
      if (closed) return;
      if (e.code === NOT_FOUND_CLOSE) {
        closed = true;
        handlers.onStatus("not_found");
        return;
      }
      handlers.onStatus("reconnecting");
      scheduleRetry();
    };
  };

  // Back online: reconnect now instead of waiting out the backoff.
  const onOnline = () => {
    if (!closed && !ws) {
      attempt = 0;
      open();
    }
  };
  window.addEventListener("online", onOnline);

  open();
  return {
    send(msg) {
      const text = JSON.stringify(msg);
      if (ws?.readyState === WebSocket.OPEN) ws.send(text);
      else if (queue.length < MAX_QUEUED) queue.push(text);
    },
    close() {
      closed = true;
      clearTimeout(retry);
      clearInterval(keepalive);
      window.removeEventListener("online", onOnline);
      const socket = ws;
      ws = null;
      if (socket?.readyState === WebSocket.CONNECTING) {
        // closing a socket that hasn't opened yet logs a browser warning; close it once it opens instead
        socket.onopen = () => socket.close(1000);
        socket.onmessage = null;
        socket.onclose = null;
      } else {
        socket?.close(1000);
      }
      handlers.onStatus("closed");
    },
  };
}
