import type {
  ApiError as ApiErrorEnvelope,
  Health,
  ProblemPublic,
  ProblemSummary,
  Project,
  ProjectSource,
  Report,
  Session,
  SessionConfig,
  TimelineEvent,
} from "@/types/contracts";

// REST client for the backend (PLAN §8.1). Every error comes back as {error: {code, message}}; this turns it
// into an ApiError the pages can show. The base URL is NEXT_PUBLIC_API_URL (default: the local backend).

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
export const WS_URL = (process.env.NEXT_PUBLIC_WS_URL || API_URL.replace(/^http/, "ws")).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const TIMEOUT_MS = 20_000;
const CREATE_TIMEOUT_MS = 45_000; // creating a session plans it (problem pick, project load)

async function send(path: string, init?: RequestInit, timeoutMs = TIMEOUT_MS): Promise<Response> {
  try {
    return await fetch(`${API_URL}${path}`, {
      ...init,
      signal: AbortSignal.timeout(timeoutMs),
      headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    });
  } catch (err) {
    if (err instanceof DOMException && (err.name === "TimeoutError" || err.name === "AbortError")) {
      throw new ApiError(0, "timeout", "The Ares server took too long to answer. Try again in a moment.");
    }
    throw new ApiError(0, "network", `Can't reach the Ares server at ${API_URL}. Is the backend running?`);
  }
}

async function fail(res: Response): Promise<never> {
  const body = (await res.json().catch(() => null)) as ApiErrorEnvelope | null;
  throw new ApiError(res.status, body?.error?.code ?? `http_${res.status}`, body?.error?.message ?? res.statusText);
}

async function json<T>(path: string, init?: RequestInit, timeoutMs?: number): Promise<T> {
  const res = await send(path, init, timeoutMs);
  if (!res.ok) return fail(res);
  return (await res.json()) as T;
}

export type ReportResult = { status: "ready"; report: Report } | { status: "generating" };

export const api = {
  health: () => json<Health>("/api/health"),
  problems: () => json<ProblemSummary[]>("/api/problems"),
  problem: (slug: string) => json<ProblemPublic>(`/api/problems/${encodeURIComponent(slug)}`),
  samples: () => json<Project[]>("/api/defense/samples"),
  projectFiles: (id: string) => json<ProjectSource>(`/api/defense/projects/${encodeURIComponent(id)}/files`),
  createSession: (config: SessionConfig) =>
    json<Session>("/api/sessions", { method: "POST", body: JSON.stringify(config) }, CREATE_TIMEOUT_MS),
  session: (id: string) => json<Session>(`/api/sessions/${encodeURIComponent(id)}`),
  endSession: (id: string) => json<Session>(`/api/sessions/${encodeURIComponent(id)}/end`, { method: "POST" }),
  timeline: (id: string) => json<TimelineEvent[]>(`/api/sessions/${encodeURIComponent(id)}/timeline`),
  /** The report once it's built; `generating` (202) while it isn't yet. */
  report: async (id: string): Promise<ReportResult> => {
    const res = await send(`/api/sessions/${encodeURIComponent(id)}/report`);
    if (res.status === 202) return { status: "generating" };
    if (!res.ok) return fail(res);
    return { status: "ready", report: (await res.json()) as Report };
  },
};

/** A message for the person at the screen, whatever went wrong. */
export function errorText(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return err instanceof Error ? err.message : "Something went wrong.";
}
