// Sample data shared with the backend: these JSON files are copies of
// backend/tests/fixtures/*.json on feat/contracts-v1, typed against the generated contracts.
// The landing fragments and the /demo routes read them; a live session reads only
// ServerMessages. Re-copy them when the backend fixtures change; don't edit them here.

import type {
  Analysis,
  AuditResult,
  ChaosRun,
  IntegrityFlag,
  Intervention,
  ProblemPublic,
  Project,
  Report,
  RunResult,
  ServerMessage,
  Session,
  TimelineEvent,
  TranscriptTurn,
} from "@/types/contracts";
import analysisJson from "./analysis.json";
import attackJson from "./attack_functions.json";
import auditJson from "./audit_result.json";
import problemJson from "./problem_public.json";
import projectJson from "./project.json";
import reportCodingJson from "./report_coding.json";
import reportDefenseJson from "./report_defense.json";
import serverMessagesJson from "./server_messages.json";
import sessionJson from "./session.json";
import timelineJson from "./timeline_events.json";

export const problem = problemJson as ProblemPublic;
export const codingSession = sessionJson as Session;
export const analysis = analysisJson as Analysis;
export const timeline = timelineJson as TimelineEvent[];
export const serverMessages = serverMessagesJson as ServerMessage[];
export const codingReport = reportCodingJson as Report;
export const project = projectJson as Project;
export const audit = auditJson as AuditResult;
export const defenseReport = reportDefenseJson as Report;

// ---------- coding: Quiet Streak ----------

function message<T extends ServerMessage["type"]>(type: T) {
  const msg = serverMessages.find((m) => m.type === type);
  if (!msg) throw new Error(`fixture missing ${type}`);
  return msg as Extract<ServerMessage, { type: T }>;
}

export const sessionState = message("session.state");
export const nudge: Intervention = message("interviewer.message").intervention;
export const submitResult: RunResult = message("run.result").result;
export const pasteFlag: IntegrityFlag = message("integrity.flag").flag;

const payloads = <T>(kind: TimelineEvent["kind"]) =>
  timeline.filter((e) => e.kind === kind).map((e) => e.payload as unknown as T);

export const visibleRun: RunResult = payloads<RunResult>("run")[0];
export const tabFlag: IntegrityFlag = payloads<IntegrityFlag>("integrity")[0];
export const transcript: TranscriptTurn[] = [
  ...payloads<TranscriptTurn>("transcript"),
  message("transcript.update").turn,
];

// StepProgress carries only a step_id, so the titles and the s2 hint ladder come from the
// problem's rubric (problem_spec.json), which never reaches the browser in a live session.
export const STEP_TITLES: Record<string, string> = {
  s1: "Clarify the input",
  s2: "Count a streak that reaches the end",
};
export const S2_HINTS = [
  { level: "nudge", text: "Look at what happens on your last reading." },
  { level: "question", text: "If the longest quiet stretch is at the very end, when does your code record it?" },
  { level: "hint", text: "A streak can end because the list ends, not only because of a loud reading." },
] as const;
export const WRAP_UP_QUESTION = "What are the time and space complexity?";
export const CLARIFY_QUESTION = "Can a reading equal to the threshold count as quiet?";

// A candidate's in-progress draft with the m1 mistake the analysis flags on line 7:
// best only updates on a loud reading, so a streak that runs to the end is lost.
export const DRAFT_CODE = `def longest_quiet_streak(readings: list[int], threshold: int) -> int:
    best = cur = 0
    for r in readings:
        if r < threshold:
            cur += 1
        else:
            best = max(best, cur)
            cur = 0
    return best
`;

export const FIXED_CODE = `def longest_quiet_streak(readings: list[int], threshold: int) -> int:
    best = cur = 0
    for r in readings:
        if r < threshold:
            cur += 1
        else:
            best = max(best, cur)
            cur = 0
    best = max(best, cur)
    return best
`;

/** True once the draft also records a streak that is still running when the loop ends. */
export function recordsTrailingStreak(code: string) {
  return (
    /^ {4}(best\s*=\s*max\(\s*best\s*,\s*cur\s*\)|return\s+max\(\s*best\s*,\s*cur\s*\))/m.test(code) ||
    // or updates best on every quiet reading, right after the count grows
    /cur\s*\+=\s*1\s*\n {12}best\s*=\s*max\(\s*best\s*,\s*cur\s*\)/.test(code)
  );
}

// ---------- defense: bank-transfer ----------

export const finding = audit.findings[0];
const runs = defenseReport.defense!.chaos_runs;
export const baselineRun = runs.find((r) => r.kind === "baseline") as ChaosRun;
export const verifyRun = runs.find((r) => r.kind === "verify") as ChaosRun;
export const grillTurn = defenseReport.defense!.grill[0];
export const verdict = defenseReport.defense!.verdict;

/** The last metric sample of a chaos run: what the run ended on. */
export const lastMetric = (run: ChaosRun) => run.metrics[run.metrics.length - 1];

/** "total 8760, expected 10000" → dollars missing. */
export function missingDollars(run: ChaosRun) {
  const m = /total (\d+), expected (\d+)/.exec(run.detail);
  return m ? Number(m[2]) - Number(m[1]) : 0;
}

// ---------- shared formatting ----------

export const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

const DIMENSION_LABEL: Record<string, string> = {
  problem_solving: "Problem solving",
  correctness: "Correctness",
  code_quality: "Code quality",
  communication: "Communication",
  independence: "Independence",
  debugging: "Debugging",
  system_understanding: "System understanding",
};
export const dimensionLabel = (name: string) => DIMENSION_LABEL[name] ?? name;

const SEVERITY_LABEL = { low: "Low", medium: "Medium", high: "High", critical: "Critical" } as const;
export const severityLabel = (s: keyof typeof SEVERITY_LABEL) => SEVERITY_LABEL[s];

export const levelLabel = (level: string) => level.charAt(0).toUpperCase() + level.slice(1);

// ---------- defense: the bank-transfer sample's files ----------

// The real sample app is DATA-4 (Sharvil); until it lands, this is an illustrative copy built to the
// fixture's facts: /transfer on lines 41–58 reads the balance, awaits the fraud check, then writes.
// The model-written bodies the chaos template wraps (PLAN §11.4); backend-only, so not in contracts.ts.
type AttackFunctions = { setup_body: string; request_body: string; invariant_body: string; rationale: string };
export const attackFunctions = attackJson as AttackFunctions;

const MAIN_PY = `import asyncio

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.accounts import Accounts

app = FastAPI()
accounts = Accounts.seed(total=10_000)


class Transfer(BaseModel):
    sender: str = Field(alias="from")
    to: str
    amount: int


@app.get("/accounts")
async def list_accounts():
    return [{"id": a.id, "balance": a.balance} for a in accounts.all()]


@app.get("/accounts/{account_id}")
async def get_account(account_id: str):
    account = accounts.get(account_id)
    if account is None:
        raise HTTPException(404, "no such account")
    return {"id": account.id, "balance": account.balance}


async def fraud_check(t: Transfer) -> bool:
    # stands in for a call to an external risk service
    await asyncio.sleep(0.03)
    return t.amount < 5_000


# Moves money between two accounts. Balances live in memory, so
# every request in this process sees the same Account objects.


@app.post("/transfer")
async def transfer(t: Transfer):
    sender = accounts.get(t.sender)
    receiver = accounts.get(t.to)
    if sender is None or receiver is None:
        raise HTTPException(404, "no such account")

    balance = sender.balance
    if balance < t.amount:
        raise HTTPException(400, "insufficient funds")

    if not await fraud_check(t):
        raise HTTPException(403, "flagged for review")

    sender.balance = balance - t.amount
    receiver.balance += t.amount

    return {"ok": True, "balance": sender.balance}
`;

const ACCOUNTS_PY = `from dataclasses import dataclass


@dataclass
class Account:
    id: str
    balance: int


class Accounts:
    def __init__(self, accounts: list[Account]):
        self._by_id = {a.id: a for a in accounts}

    @classmethod
    def seed(cls, total: int, count: int = 10) -> "Accounts":
        share = total // count
        return cls([Account(f"acc-{i + 1}", share) for i in range(count)])

    def get(self, account_id: str) -> Account | None:
        return self._by_id.get(account_id)

    def all(self) -> list[Account]:
        return list(self._by_id.values())
`;

/** The project's Python files as the fix stage opens them, keyed by path. */
export const BANK_FILES: Record<string, string> = {
  "app/main.py": MAIN_PY,
  "app/accounts.py": ACCOUNTS_PY,
};

/** True once the balance read and write can't interleave: a lock held across them. */
export function transferIsAtomic(mainPy: string) {
  return /asyncio\.Lock\(\)/.test(mainPy) && /async with\s+\w+/.test(mainPy);
}
