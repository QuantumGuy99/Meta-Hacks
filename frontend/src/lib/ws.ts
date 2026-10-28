import type { ClientMessage, ServerMessage } from "@/types/contracts";
import { WS_URL } from "./api";

// The session WebSocket (PLAN §8.2): JSON both ways. It says `hello` on every (re)connect so the server
// replies with the current session.state, reconnects with backoff, and queues what the room sends while the
// connection is down (the capture lib's next snapshot covers anything that doesn't fit the queue).

export type SocketStatus = "connecting" | "open" | "reconnecting" | "closed" | "not_found";

export type SessionSocket = { send: (msg: ClientMessage) => void; close: () => void };

const NOT_FOUND_CLOSE = 4404;
const BACKOFF_MS = [500, 1000, 2000, 4000, 8000];
const MAX_QUEUED = 500;

export function connectSession(
  id: string,
  handlers: { onMessage: (msg: ServerMessage) => void; onStatus: (status: SocketStatus) => void },
): SessionSocket {
  let ws: WebSocket | null = null;
  let attempt = 0;
  let closed = false;
  let retry: ReturnType<typeof setTimeout> | undefined;
  const queue: string[] = [];

  const open = () => {
    handlers.onStatus(attempt === 0 ? "connecting" : "reconnecting");
    const socket = new WebSocket(`${WS_URL}/ws/sessions/${encodeURIComponent(id)}`);
    ws = socket;
    socket.onopen = () => {
      attempt = 0;
      handlers.onStatus("open");
      socket.send(JSON.stringify({ type: "hello", client_now_ms: Date.now() } satisfies ClientMessage));
      while (queue.length) socket.send(queue.shift()!);
    };
    socket.onmessage = (e) => {
      try {
        handlers.onMessage(JSON.parse(String(e.data)) as ServerMessage);
      } catch {
        // not JSON: ignore it rather than break the room
      }
    };
    socket.onclose = (e) => {
      if (ws === socket) ws = null;
      if (closed) return;
      if (e.code === NOT_FOUND_CLOSE) {
        closed = true;
        handlers.onStatus("not_found");
        return;
      }
      handlers.onStatus("reconnecting");
      retry = setTimeout(open, BACKOFF_MS[Math.min(attempt++, BACKOFF_MS.length - 1)]);
    };
  };

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
      ws?.close(1000);
      ws = null;
      handlers.onStatus("closed");
    },
  };
}
