# Crucible build plan

This is the single source of truth for building Crucible during the Meta Global AI Developer Hackathon
(building period **Tue Oct 27 – Wed Nov 4, 2026; submission due Wed Nov 4, 9:00 PM ET**). The
[README](README.md) says *what* Crucible is; this file says *how*: scope, architecture, contracts, algorithms,
work packages, owners and schedule. It is written so a coding agent (Muse Code, Claude Code) can pick up any
work package and build it.

**Coding agents: read §0 and §22 before writing any code.**

---

## Contents

0. [How to use this plan](#0-how-to-use-this-plan)
1. [Product summary](#1-product-summary)
2. [Scope and priorities](#2-scope-and-priorities)
3. [User flows](#3-user-flows)
4. [Architecture](#4-architecture)
5. [Tech stack](#5-tech-stack)
6. [Repository layout and ownership](#6-repository-layout-and-ownership)
7. [Contracts](#7-contracts)
8. [API: REST and WebSocket](#8-api-rest-and-websocket)
9. [Shared interviewer engine](#9-shared-interviewer-engine)
10. [Mode A: Live Coding Interview](#10-mode-a-live-coding-interview)
11. [Mode B: Project Defense](#11-mode-b-project-defense)
12. [Runner](#12-runner)
13. [Data](#13-data)
14. [Frontend](#14-frontend)
15. [Meta model integration](#15-meta-model-integration)
16. [Work packages](#16-work-packages)
17. [Schedule](#17-schedule)
18. [Testing and evals](#18-testing-and-evals)
19. [Deployment](#19-deployment)
20. [Demo video and submission](#20-demo-video-and-submission)
21. [Risks and fallbacks](#21-risks-and-fallbacks)
22. [Rules for coding agents](#22-rules-for-coding-agents)
23. [Things to verify](#23-things-to-verify)

---

## 0. How to use this plan

- Every piece of work is a **work package** in §16 with an ID (`ENG-3`, `DEF-4`, …), an owner, its
  dependencies and a "done when" list. A PR should close one work package or a clearly named part of one.
- **P0** = must ship for the demo. **P1** = should ship. **P2** = stretch, only after both P0 paths pass the
  demo script twice in a row on the deployed build.
- Anything marked **⚠️ VERIFY** is an API detail we couldn't confirm from the docs. Check the linked doc before
  coding against it, then update this file. The full list is in §23.
- When this plan and the code disagree, fix whichever is wrong in the same PR. Don't let them drift.
- **Per-person plans** are in [`plan/`](plan/README.md): each teammate's slice of this file (owned paths,
  handoffs with dates, build order, a brief for each work package). This file is the spec. If a role plan
  disagrees with it, this file wins, and the role plan gets fixed in the same PR.

---

## 1. Product summary

Crucible is a web app with **one live AI interviewer** and **two modes**:

- **Live Coding Interview** (`mode = "coding"`): an original algorithm problem, a Python editor and an
  interviewer that watches the edit stream and your think-aloud speech as they happen. In **active** feedback
  it steps in (nudges, Socratic questions, escalating hints); in **passive** feedback it stays quiet and
  reports at the end. Either way it records **how** you solved the problem.
- **Project Defense** (`mode = "defense"`): you submit a small Python web project. Crucible audits it,
  **breaks it under load** in a sandbox, grills you by voice on why it broke, watches you fix it in the same
  live editor and re-runs the attack to verify the fix. The result is a pass/fail "merge gate".

Both modes share: the interview room (editor + interviewer panel + voice), the timeline, the analyzer/policy
engine, the runner and the report/replay. **The shared engine is the product**; each mode is a different
source of problems plus a few mode-specific stages.

**Pitch:** *"LeetCode grades your answer. Crucible grades your engineering, whether you wrote the code or your
AI did."*

**Problem statement fit (Build for Your World):** we're students preparing for technical interviews and using
coding agents daily. Both modes solve problems we have firsthand.

---

## 2. Scope and priorities

### Feature table

| Area | P0 (demo-critical) | P1 (should) | P2 (stretch) |
|---|---|---|---|
| **Room** | Monaco editor (Python), edit capture, interviewer panel, text chat, timer, phase stepper | Voice in (Muse Voice Transcribe), voice out (browser TTS), "interviewer's notes" panel | Multi-language (JS) |
| **Coding mode** | 12 validated problems, difficulty picker, run/submit tests, analyzer + policy (active and passive), hint ladder, paste/tab notes, report | 30 problems, plan-vs-code check, coded-before-plan check, wrap-up complexity question, problem illustrations | 40+ problems, SAM 3.1 paper sketch, proctor mode |
| **Defense mode** | 3 sample apps, Wonder audit + topology diagram, chaos run (breaks before the fix, holds after), grill (text answers OK), fix in editor, verify, verdict | Voice grill, "circle the flaw" with SAM 3.1, Muse fix assistant (DEF-11, logged), attack refine loop, zip upload, 5 sample apps | GitHub URL import, suggested refactor patch / Muse Code handoff, Muse Image merge-gate card |
| **Report** | Scores, summary, strengths/improvements, metrics, moments, replay (code playback + transcript + nudges) | Defense before/after charts in the report, share link | Muse Image report card |
| **Platform** | Local dev, MOCK mode, SQLite, deployed frontend + backend | Spend guard (sessions per IP per day), contributor-model dev switch | Accounts (not planned) |

### Non-goals (do not build)
- Accounts, payments, teams, history across sessions. Sessions are anonymous; the session URL is the key.
- Languages other than Python (P2 at most).
- Arbitrary projects in Defense mode. Python 3.12 web apps (FastAPI/Flask) under the limits in §11.1 only.
- Vitals or emotion detection. Medical-adjacent features are off-theme and risky.
- Any problem text copied from LeetCode or other sites (rights risk → disqualification).
- Fake or mocked flows in the demo video. MOCK mode is for frontend development only.

---

## 3. User flows

### 3.1 Live Coding Interview
1. `/` → choose **Live Coding Interview**.
2. `/coding` setup: difficulty (easy/medium/hard), optional topic, feedback **active/passive**, voice on/off,
   "speak replies" on/off. → `POST /api/sessions` → redirect to `/coding/{id}`.
3. **Intro** (≈30 s): the interviewer greets and presents the problem (text + TTS). The problem panel shows
   the statement, examples and constraints.
4. **Clarify:** the candidate asks questions (voice or chat) and states an approach. The interviewer answers
   clarifying questions from the problem spec only. The editor is unlocked the whole time; coding before
   stating an approach is allowed but noted (P1 rule).
5. **Coding:** edits stream to the backend. The analyzer runs on typing pauses; the policy decides on
   interventions. The candidate can press **Run** (visible tests), **Submit** (all tests), **Ask** (direct
   question) or **Hint** (explicit hint request, counted).
6. **Wrap up:** after an accepted submit, or when time runs out, the interviewer asks one complexity question
   and one edge-case/trade-off question.
7. **Ended → report:** `/report/{id}` shows a "generating" state until `report.ready`, then the report.

### 3.2 Project Defense
1. `/` → choose **Project Defense** → `/defense`: pick a sample app (P0) or upload a zip (P1).
2. **Ingest:** the backend validates and stores the project, then creates the session → `/defense/{id}`.
3. **Audit:** Wonder returns findings + topology. The UI shows the React Flow diagram with flagged nodes and a
   findings list. The top findings (max 3, P0 = 1–2) with a `chaos` plan are queued.
4. **Chaos (per finding):** generate the attack script → validate → run in the sandbox → stream metrics →
   verdict `broke`/`held`. If a finding doesn't break the app, it's dropped from the grill (or refined by the
   agent loop in P1).
5. **Grill (per broken finding):** the interviewer asks the grill question, referencing the real numbers. The
   candidate answers (voice or text). At most one follow-up and a 90 s cap per finding. Each answer is graded
   against the expected points.
6. **Fix:** the room opens the relevant file(s) in Monaco with the same live engine running a "fix rubric".
7. **Verify:** re-run the same attack script against the edited code → `held` required.
8. **Verdict:** gate PASS if every grilled finding is verified fixed **and** the average grill score is ≥ 6/10.
   → report.

---

## 4. Architecture

### 4.1 Components

```
Browser (Next.js)
 ├─ InterviewRoom (shared): Monaco · EditorCapture · AudioCapture · InterviewerPanel · TestPanel
 ├─ Coding pages (setup, room)      ├─ Defense pages (picker, audit, chaos, grill, fix, verdict)
 └─ Report + Replay
        │  WS /ws/sessions/{id}         (JSON messages, §8.2)
        │  WS /ws/sessions/{id}/audio   (binary PCM 24 kHz frames)
        │  REST /api/*                  (§8.1)
Backend (FastAPI)
 ├─ store/      SQLite: sessions, events (timeline), reports, projects, audits
 ├─ engine/     SessionHub (WS fan-out) · Timeline · CodeState · Analyzer · Policy · Interviewer ·
 │              VoiceBridge · ReportBuilder
 ├─ coding/     ProblemBank · CodingSession (phases/timers) · RunService · IntegrityDetector
 ├─ defense/    ProjectStore · Auditor · ChaosLab · Grill · FixVerifier · Verdict
 ├─ runner/     Runner protocol · LocalRunner (dev) · ModalRunner · harness/
 └─ models/     llm.py (Meta OpenAI-compatible) · asr.py · image.py · sam.py · registry.py
External: Meta Model API · Modal · Baseten (Spark Open)
```

### 4.2 One "tick" in a coding session (the core loop)

```
Monaco change ──► EditorCapture batches 500 ms ──► WS editor.events ──► SessionHub
   ──► Timeline.append(editor) ──► CodeState.apply() ──► IntegrityDetector (paste? tab?)
   ──► AnalyzerScheduler: typing paused ≥ 2.5 s AND code changed AND ≥ 8 s since last analysis?
          └─► Analyzer.run() ──► Muse Spark 1.3 (structured output: Analysis, §7.3)
                 └─► Timeline.append(analysis) ──► Policy.decide(analysis, state)
                        ├─ no  → nothing (passive mode: log a suppressed intervention)
                        └─ yes → Interviewer.phrase() ──► leak guard ──► Timeline.append(intervention)
                                   ──► WS interviewer.message ──► panel + TTS
```

Runs, final transcript turns and explicit asks also trigger the scheduler (§9.4).

### 4.3 One chaos run in Defense mode

```
Finding.chaos (plan) ──► AttackWriter (Spark → reference attack) fills 3 functions in the template
   ──► ScriptValidator (AST allowlist) ──► ModalRunner.start_project(files) ──► readiness probe
   ──► exec attack.py ──► stdout JSON lines ──► ChaosMetric ──► Timeline + WS defense.chaos.metric
   ──► final line {done, invariant_ok, detail} ──► ChaosRun.verdict ──► WS defense.chaos.done
```

### 4.4 Design rules (enforced in review)
1. **Contracts first.** `backend/crucible/contracts/` is the only place message shapes are defined. TS types
   are generated (`make contracts`); never hand-edit `frontend/src/types/contracts.ts`. CI fails on drift.
2. **The LLM suggests, code decides.** Models return structured proposals; Python code decides whether, when
   and at what level anything reaches the user.
3. **The timeline is the source of truth.** If it's not a timeline event, the report can't use it.
4. **Every external call has a timeout and a fallback** (table in §21).
5. **Never hand over the solution.** Leak guard on every interviewer message (§9.6).
6. **Neutral integrity.** Pastes and tab switches are facts in the report, never accusations.
7. **Secrets stay server-side.** The browser never receives an API key. Audio goes through the backend proxy.
8. **Real demo.** MOCK mode exists for frontend development only.

---

## 5. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | **Python 3.12**, **FastAPI**, uvicorn, **Pydantic v2**, pydantic-settings | Python because Modal's SDK and the harness are Python |
| Package mgmt | **uv** (backend), **pnpm** via corepack (frontend) | Node ≥ 22 (Next 16 and shadcn's `cn` package require it; Node 24 works) |
| LLM client | **`openai` Python SDK** with `base_url="https://api.meta.ai/v1"` | Meta's API is OpenAI-compatible; pass `api_key` explicitly |
| ASR client | `websockets` (Python) | Backend proxies to `wss://api.meta.ai/v1/asr/realtime` |
| Storage | **SQLite** via SQLModel (file at `DATABASE_URL`) | One file; volume-mounted when deployed |
| Code execution | **Modal Sandboxes** (`modal` SDK); `LocalRunner` subprocess for dev | |
| Frontend | **Next.js 16** (App Router, Turbopack) + **React 19** + TypeScript, **Tailwind v4**, **shadcn/ui** (`base-nova` style, Base UI primitives) | Desktop-first (≥ 1280 px); an editor app. Next 16 changed APIs, so read `frontend/AGENTS.md` before writing frontend code |
| UI rules | [`frontend-schematic/UI_TEMPLATE.md`](frontend-schematic/UI_TEMPLATE.md): dark theme tokens, one accent, Hanken Grotesk (Geist Mono only in code), taste-skill look + Vercel's Web Interface Guidelines | Every screen is checked against it before its PR. Lives on the `frontend` branch until it merges |
| Editor | `@monaco-editor/react` | Disable quick suggestions to keep it interview-like |
| Diagram / charts | `@xyflow/react` (React Flow) with `@dagrejs/dagre` auto-layout, **Recharts** | |
| Other frontend libs | `react-markdown` (problem statements), `motion` (state-change animation), `lucide-react` (icons) | Each listed in the PR that adds it (§22 rule 12) |
| Client state | **zustand** | One store per session |
| TTS | Browser **`speechSynthesis`** | Meta has no TTS model; this is free and needs no key |
| Lint/test | ruff, pytest, pytest-asyncio; eslint, tsc, Playwright (P1) | |
| CI | GitHub Actions: `make check` | |
| Hosting | Frontend **Vercel**; backend **Railway** or **Fly.io** (Docker, WebSockets, volume) | |

---

## 6. Repository layout and ownership

Owners: **SG** Srinithin Ganesh · **SS** Shreyas Sahoo · **LG** Likhil Gudipati · **ST** Sharvil Talware.

```
.
├── README.md · PLAN.md · LICENSE
├── plan/                            # one plan per teammate: their slice of this file        (each owner)
├── frontend-schematic/              # LG's detailed frontend plan + UI rules (UI_TEMPLATE.md) (LG)
├── Makefile                         # install, dev, check, contracts, validate, evals, mock  (SS)
├── .env.example                     # every variable, documented                              (SS)
├── .github/workflows/ci.yml         # make check                                              (SS)
├── backend/
│   ├── pyproject.toml · Dockerfile                                                            (SS)
│   ├── crucible/
│   │   ├── main.py                  # app factory, routers, CORS, lifespan                    (SS)
│   │   ├── config.py                # Settings from env                                      (SS)
│   │   ├── contracts/               # 🔒 SG + SS approve every change
│   │   │   ├── common.py events.py coding.py defense.py report.py ws.py
│   │   │   └── export.py            # → frontend/src/types/contracts.ts
│   │   ├── store/                   # db.py, repo.py (sessions, events, reports, projects)   (SS)
│   │   ├── models/                  # llm.py asr.py image.py sam.py registry.py   (SG; SS may write
│   │   │                            #   sam.py / image.py for DEF-9 / DEF-10 if SG agrees)
│   │   ├── engine/                  # shared interviewer engine                              (SG)
│   │   │   ├── hub.py               # SessionHub: WS connections, fan-out, routing
│   │   │   ├── timeline.py          # append/read, seq, typed payload helpers
│   │   │   ├── codestate.py         # reconstruct code from edits + snapshots, diffs, counters
│   │   │   ├── analyzer.py          # scheduler + LLM call → Analysis
│   │   │   ├── policy.py            # rules, cooldowns, hint ladder, passive mode
│   │   │   ├── interviewer.py       # phrasing, replies to asks, phase lines, leak guard
│   │   │   ├── voice.py             # VoiceBridge (ASR proxy) + fallbacks
│   │   │   ├── report.py            # metrics, moments, ReportDraft (Wonder), merge
│   │   │   └── prompts/*.md         # every prompt lives in a file, never inline
│   │   ├── coding/                  # problems.py session.py tests.py integrity.py prompts/  (SG)
│   │   ├── defense/                 # controller.py projects.py audit.py chaos.py attack_writer.py
│   │   │                            # validator.py grill.py verify.py verdict.py card.py prompts/ (SS)
│   │   ├── runner/                  # base.py local.py modal_runner.py                       (SS)
│   │   │   └── harness/             # run_tests.py chaos_template.py (baked into the sandbox image)
│   │   ├── datatools/               # draft_problem.py validate_problems.py validate_apps.py (ST)
│   │   ├── vision/                  # P2: sketch.py proctor.py (SAM 3.1)                     (SG)
│   │   └── mock/                    # replay.py + fixtures/*.jsonl                           (SS; fixtures SG+SS)
│   └── tests/                       # mirrors crucible/ ; evals in tests/evals/
├── data/                                                                                    (ST)
│   ├── problems/<slug>/problem.json · statement.md · reference.py · brute.py · illustration.png
│   ├── defense_apps/<slug>/app/ · requirements.txt · crucible.json · flaws.json · fix.patch
│   └── evals/coding/*.jsonl · evals/defense/*.json
└── frontend/                                                                                (LG unless noted)
    └── src/
        ├── app/                     # /, /coding, /coding/[id], /defense, /defense/[id], /report/[id]
        ├── components/
        │   ├── room/                # InterviewRoom, Editor, InterviewerPanel, TestPanel, NotesPanel
        │   ├── coding/  defense/  report/  ui/ (shadcn)
        ├── lib/
        │   ├── api.ts ws.ts store.ts          (LG)
        │   ├── capture/editor.ts              (SG)  Monaco → EditorEvent batches + snapshots
        │   ├── capture/audio/*                (SG)  mic → AudioWorklet → PCM 24 kHz Int16 frames
        │   ├── replay.ts                      (SG)  code at time t (mirrors engine/codestate.py)
        │   ├── tts.ts                         (SG)  interviewer voice, speechSynthesis (LG reviews)
        │   └── defense.ts                     (SS)  defense-stage helpers/selectors
        └── types/contracts.ts                 # GENERATED (make contracts); do not edit
```

**Rule:** backend owners also write the *non-visual* client code for their protocol (capture, replay,
selectors). Likhil owns every component and page. This keeps protocol code next to the person who designed it
and keeps the frontend workload manageable.

---

## 7. Contracts

All contract models inherit `Strict` (`extra="forbid"`). Times `t` are **integer milliseconds since the session
started** (`session.started_at`). IDs are short random strings (`uuid4().hex[:12]`) unless noted.

**LLM output models** (`Analysis`, `InterventionText`, `AuditResult`, `AttackFunctions`, `GrillEval`,
`ReportDraft`) are used as structured-output schemas. For strict mode: **no default values, every field
required, use `X | None` for optional, no recursive types, nesting depth ≤ 10.**

### 7.1 `common.py`

```python
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Mode(StrEnum):
    CODING = "coding"
    DEFENSE = "defense"

class Difficulty(StrEnum):
    EASY = "easy"; MEDIUM = "medium"; HARD = "hard"

class FeedbackLevel(StrEnum):
    ACTIVE = "active"; PASSIVE = "passive"

class Phase(StrEnum):
    SETUP = "setup"
    # coding
    INTRO = "intro"; CLARIFY = "clarify"; CODING = "coding"; WRAP_UP = "wrap_up"
    # defense
    AUDIT = "audit"; CHAOS = "chaos"; GRILL = "grill"; FIX = "fix"; VERIFY = "verify"; VERDICT = "verdict"
    # both
    ENDED = "ended"; REPORTING = "reporting"; REPORTED = "reported"; FAILED = "failed"

class SessionConfig(Strict):
    mode: Mode
    feedback: FeedbackLevel = FeedbackLevel.ACTIVE
    voice: bool = True               # mic + Muse Voice Transcribe
    speak_replies: bool = True       # browser TTS for interviewer messages
    proctor: bool = False            # P2: SAM 3.1 webcam checks (opt-in)
    problem_slug: str | None = None  # coding: explicit problem
    difficulty: Difficulty | None = None  # coding: random problem at this difficulty
    topic: str | None = None
    project_id: str | None = None    # defense
    time_limit_s: int | None = None  # default from problem/difficulty

class Session(Strict):
    id: str
    config: SessionConfig
    phase: Phase
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    time_limit_s: int
    problem_slug: str | None
    project_id: str | None
```

### 7.2 `events.py` (timeline and live events)

```python
class EditorChange(Strict):
    range_offset: int        # Monaco rangeOffset (offset in the model BEFORE this event)
    range_length: int        # Monaco rangeLength
    text: str                # inserted text

class EditorEvent(Strict):
    t: int
    file: str = "solution.py"
    version: int             # Monaco model versionId after the event
    kind: Literal["change", "paste", "undo", "redo", "focus", "blur", "hidden", "visible"]
    changes: list[EditorChange] = []
    pasted_chars: int | None = None

class CodeSnapshot(Strict):
    t: int
    file: str
    version: int
    code: str

class TranscriptTurn(Strict):
    turn_id: str
    speaker: Literal["candidate", "interviewer"]
    text: str
    start_ms: int
    end_ms: int
    final: bool
    source: Literal["voice", "text"]

class CaseResult(Strict):         # named to avoid pytest collecting Test* classes
    id: str
    visible: bool
    passed: bool
    input_repr: str | None       # hidden tests: None (never sent to the browser)
    expected_repr: str | None
    actual_repr: str | None
    error: str | None
    runtime_ms: int

class RunResult(Strict):
    run_id: str
    t: int
    kind: Literal["run", "submit"]
    passed: int
    total: int
    cases: list[CaseResult]
    stdout: str                  # truncated to 4 KB
    stderr: str                  # truncated to 4 KB
    timed_out: bool
    compile_error: str | None

class InterventionTrigger(StrEnum):
    IDLE = "idle"; SILENT = "silent"; RUN_FAILED = "run_failed"; MISSED_STEP = "missed_step"
    BUG_SUSPECTED = "bug_suspected"; PLAN_MISMATCH = "plan_mismatch"; CODED_BEFORE_PLAN = "coded_before_plan"
    PASTE = "paste"; ASKED = "asked"; HINT_REQUESTED = "hint_requested"; TIME_WARNING = "time_warning"
    PHASE = "phase"; PRAISE = "praise"; GRILL = "grill"
    WARMUP = "warmup"; REPLY = "reply"; PROBE = "probe"   # conversation, not help (§10.1, §9.5)

class InterventionLevel(StrEnum):
    INFO = "info"; NUDGE = "nudge"; QUESTION = "question"; HINT = "hint"; CONCEPT = "concept"

class Intervention(Strict):
    id: str
    t: int
    trigger: InterventionTrigger
    level: InterventionLevel
    text: str
    step_id: str | None
    speak: bool
    suppressed: bool             # passive mode: decided but not shown; still in the report

class InterventionText(Strict):  # LLM output of Interviewer.phrase()
    text: str

class TurnLabel(Strict):         # LLM output of the voice classifier (COD-6, §9.7)
    label: Literal["question_to_interviewer", "thinking_aloud"]

class IntegrityFlag(Strict):
    id: str
    t: int
    kind: Literal["paste", "bulk_insert", "tab_hidden", "phone_in_frame", "extra_person"]
    detail: str
    chars: int | None
    duration_ms: int | None

class ModelActivity(Strict):  # the "Under the hood" strip (docs/STORY.md): labels only, never content
    call_id: str                 # pairs a call's "started" with how it ended
    t: int
    model_name: Literal["Muse Spark", "Muse Wonder", "Muse Spark Open", "Muse Voice", "SAM 3.1", "Muse Image"]
    task: str                    # a plain verb phrase: "watching your code", "reading your project"
    status: Literal["started", "done", "fallback", "cached", "failed", "stopped"]
    latency_ms: int | None       # None while started

class TimelineKind(StrEnum):
    PHASE = "phase"; EDITOR = "editor"; SNAPSHOT = "snapshot"; TRANSCRIPT = "transcript"; RUN = "run"
    ANALYSIS = "analysis"; INTERVENTION = "intervention"; INTEGRITY = "integrity"
    AUDIT = "audit"; CHAOS_METRIC = "chaos_metric"; CHAOS_RUN = "chaos_run"; GRILL = "grill"
    SAM_HIGHLIGHT = "sam_highlight"; VERDICT = "verdict"; SYSTEM = "system"; MODEL_ACTIVITY = "model_activity"

class TimelineEvent(Strict):
    seq: int
    t: int
    kind: TimelineKind
    payload: dict                # must validate against PAYLOAD_MODELS[kind]
```

`PAYLOAD_MODELS` (in `timeline.py`): `phase → PhaseChange{from_phase, to_phase, reason}`,
`editor → EditorEvent`, `snapshot → CodeSnapshot`, `transcript → TranscriptTurn`, `run → RunResult`,
`analysis → Analysis`, `intervention → Intervention`, `integrity → IntegrityFlag`, `audit → AuditResult`,
`chaos_metric → ChaosMetric`, `chaos_run → ChaosRun`, `grill → GrillTurn`,
`sam_highlight → SamHighlight`, `verdict → Verdict`,
`system → SystemNote{level, message}`. `Timeline.append()` validates the payload before writing.

### 7.3 `coding.py`

```python
class Param(Strict):
    name: str
    type: str                    # Python annotation as text, e.g. "list[int]"

class FunctionSig(Strict):
    name: str
    params: list[Param]
    returns: str

Comparator = Literal["exact", "unordered", "float_tol", "unordered_inner", "set_of_lists"]

class CaseSpec(Strict):           # one test case (not named Test*, so pytest won't try to collect it)
    id: str
    args: list[Any]              # JSON values, positional
    expected: Any
    comparator: Comparator = "exact"
    edge_case_id: str | None = None

class Example(Strict):
    input: str
    output: str
    explanation: str | None = None

class RubricStep(Strict):
    id: str                      # "s1", "s2", ...
    title: str                   # "Handle empty input"
    description: str
    required: bool
    order: int                   # expected order (later steps depend on earlier ones)
    look_for: list[str]          # observable signals in code/speech
    hints: list[str]             # exactly 3: [nudge, question, hint]; never code

class EdgeCase(Strict):
    id: str
    description: str

class Mistake(Strict):
    id: str
    description: str
    symptom: str                 # what it looks like in code or test failures

class Approach(Strict):
    name: str                    # "hash map of complements"
    time: str                    # "O(n)"
    space: str
    acceptable: bool             # brute force is usually acceptable=False for medium/hard

class Rubric(Strict):
    approaches: list[Approach]
    steps: list[RubricStep]
    edge_cases: list[EdgeCase]
    common_mistakes: list[Mistake]
    wrap_up_questions: list[str] # 2: complexity + trade-off/edge case

class ProblemSpec(Strict):       # data/problems/<slug>/problem.json (+ statement.md, reference.py, brute.py)
    slug: str
    title: str
    difficulty: Difficulty
    topics: list[str]
    function: FunctionSig
    starter_code: str
    examples: list[Example]
    constraints: list[str]
    tests_visible: list[CaseSpec]   # 2–4
    tests_hidden: list[CaseSpec]    # 8–25, includes every edge case
    rubric: Rubric
    time_limit_min: int
    illustration: str | None        # relative path, P1
    origin_note: str                # "Original. Pattern: sliding window."
    # loaded from sibling files at load time:
    statement_md: str = ""
    reference_solution: str = ""
    brute_force_solution: str | None = None

class ProblemSummary(Strict):
    slug: str; title: str; difficulty: Difficulty; topics: list[str]

class ProblemPublic(Strict):        # what the browser receives: NO hidden tests, rubric or reference
    slug: str; title: str; difficulty: Difficulty; topics: list[str]
    statement_md: str; examples: list[Example]; constraints: list[str]
    starter_code: str; tests_visible: list[CaseSpec]; illustration_url: str | None; time_limit_min: int

class StepStatus(StrEnum):
    NOT_STARTED = "not_started"; IN_PROGRESS = "in_progress"; DONE = "done"
    INCORRECT = "incorrect"; SKIPPED = "skipped"

class StepProgress(Strict):         # LLM output
    step_id: str
    status: StepStatus
    evidence: str                   # short quote of code/speech

class SuspectedIssue(Strict):       # LLM output
    kind: Literal["bug", "edge_case", "complexity", "style"]
    line: int | None
    description: str
    mistake_id: str | None
    confidence: float               # 0..1

class InterventionProposal(Strict): # LLM output
    trigger: InterventionTrigger
    level: InterventionLevel
    step_id: str | None
    text: str
    confidence: float

class Analysis(Strict):             # LLM output of the analyzer (§9.4)
    steps: list[StepProgress]
    issues: list[SuspectedIssue]
    stated_plan: str | None
    plan_matches_code: bool | None
    chosen_approach: str | None
    explanation_quality: Literal["none", "weak", "ok", "strong"]
    proposal: InterventionProposal | None

class ComplexityClaim(Strict):      # LLM output: the bounds stated at wrap-up (COD-5, §10.5)
    time: str | None                # big-O in the rubric's variables; None if not stated
    space: str | None
```

### 7.4 `defense.py`

```python
class ProjectFile(Strict):
    path: str
    size: int

class Project(Strict):
    id: str
    name: str
    source: Literal["sample", "upload", "github"]
    entrypoint: str              # e.g. "uvicorn app.main:app --host 127.0.0.1 --port 8080"
    port: int                    # 8080 (keeps clear of the backend's :8000 under LocalRunner)
    files: list[ProjectFile]
    loc: int
    content_hash: str            # sha256 of sorted files; audit cache key

class TopologyNode(Strict):
    id: str
    label: str
    kind: Literal["route", "service", "store", "external", "worker"]
    file: str | None
    flagged: bool

class TopologyEdge(Strict):
    source: str
    target: str
    label: str | None

FindingCategory = Literal["race_condition", "blocking_io", "complexity", "resource_leak",
                          "error_handling", "security"]
Severity = Literal["low", "medium", "high", "critical"]

class ChaosPlan(Strict):
    endpoint: str                # "/transfer"
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    body_example: str | None     # JSON text
    concurrency: int             # ≤ 200
    duration_s: int              # ≤ 30
    invariant: str               # "sum of all balances stays 10000"
    p95_threshold_ms: int | None # latency findings: p95 above this = broke; None = no latency check

class GrillSpec(Strict):
    question: str
    expected_points: list[str]   # 2–4; [0] is ALWAYS the root cause (audit prompt rule), e.g.
                                 # [root cause, mechanism under concurrency/load, fix strategy]
    follow_up: str

class Finding(Strict):
    id: str
    title: str                   # neutral: names the area, not the cause ("Balance transfers under load")
    category: FindingCategory
    severity: Severity
    file: str
    line_start: int
    line_end: int
    node_id: str | None          # the TopologyNode this flaw lives in (highlighting, SAM bonus)
    explanation: str             # grading truth: never sent to the browser before this finding's grill ends
    chaos: ChaosPlan | None
    grill: GrillSpec
    fix_steps: list[RubricStep]  # rubric for the fix stage (same engine as coding mode)

class FindingPublic(Strict):     # what the browser gets until the finding's grill is graded
    id: str
    title: str
    category: FindingCategory    # same closed sets as Finding, so the TS types match exactly
    severity: Severity
    file: str
    line_start: int
    line_end: int
    node_id: str | None

class AuditResult(Strict):       # LLM output (Wonder)
    summary: str                 # must not state root causes or fixes (it's shown before the grill)
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    findings: list[Finding]      # sorted by severity, max 5

class AuditPublic(Strict):       # payload of WS defense.audit
    summary: str
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    findings: list[FindingPublic]

class AttackFunctions(Strict):   # LLM output (Spark): bodies for the template (§11.4)
    setup_body: str
    request_body: str
    invariant_body: str
    rationale: str

class ChaosMetric(Strict):
    run_id: str
    t_ms: int                    # ms since the attack started
    in_flight: int               # concurrent requests open at the end of the window
    rps: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    errors: int
    violations: int

class ChaosRun(Strict):
    id: str
    finding_id: str
    kind: Literal["baseline", "verify"]
    attempt: int
    script: str
    verdict: Literal["broke", "held", "error"]
    summary: str                 # "37 of 500 orders lost; $1,240 missing"
    detail: str
    metrics: list[ChaosMetric]

class GrillEval(Strict):         # LLM output: judgements only, NO score (code computes it, §11.5)
    points_hit: list[int]        # indexes into GrillSpec.expected_points
    points_missed: list[int]
    needs_follow_up: bool
    feedback: str                # passes the leak guard (§9.6) before it reaches the browser

class GrillTurn(Strict):
    finding_id: str
    question: str
    answer_turn_ids: list[str]
    follow_up_asked: bool
    eval: GrillEval
    sam_node_id: str | None      # node the candidate circled (P1, §11.7)
    root_cause_hit: bool         # computed: 0 in eval.points_hit
    score: int                   # computed: 0–10 (§11.5)

class SamHighlight(Strict):      # P1: candidate circled part of the diagram or a sketch (§11.7)
    finding_id: str
    source: Literal["canvas", "webcam"]
    box: list[float] | None      # [x1, y1, x2, y2] in image pixels; None = nothing found
    node_id: str | None          # node chosen by code from the box (largest overlap)

class Verdict(Strict):
    passed: bool
    reasons: list[str]
    findings_fixed: list[str]
    findings_unfixed: list[str]
    avg_grill_score: float
```

### 7.5 `report.py`

```python
class Moment(Strict):
    t: int
    kind: Literal["good", "issue", "nudge", "integrity", "milestone"]
    title: str
    detail: str
    tip: str | None

class DimensionScore(Strict):
    name: Literal["problem_solving", "correctness", "code_quality", "communication", "independence",
                  "debugging", "system_understanding"]
    score: int                   # 0–10
    evidence: str

class Metrics(Strict):           # computed in code, never by the LLM
    duration_s: int
    time_to_first_edit_s: int | None
    time_to_first_run_s: int | None
    runs: int
    submits: int
    hidden_passed: int | None
    hidden_total: int | None
    interventions_shown: int
    hints_by_level: dict[str, int]
    chars_typed: int
    chars_pasted: int
    tab_hidden_s: int
    talk_time_s: int
    longest_silence_s: int

class CandidateMoment(Strict):   # selected by code, worded by the LLM
    t: int
    kind: Literal["good", "issue", "nudge", "integrity", "milestone"]
    facts: str

class ReportDraft(Strict):       # LLM output (Wonder)
    overall: int                 # 0–100
    dimensions: list[DimensionScore]
    summary: str
    strengths: list[str]         # 3
    improvements: list[str]      # 3
    moments: list[Moment]        # one per CandidateMoment, same t

class CodingExtra(Strict):
    problem_slug: str
    steps: list[StepProgress]    # final statuses
    approach: str | None
    complexity_answer_ok: bool | None

class DefenseExtra(Strict):
    findings: list[Finding]
    chaos_runs: list[ChaosRun]   # baseline + verify runs carry the before/after metrics
    grill: list[GrillTurn]
    verdict: Verdict
    card_url: str | None         # P2: merge-gate card image (§11.8)
    # P1 (§11.9), proposed: ai_assist: AiAssistStats | None   {asks, suggestions, accepted, ai_chars,
    #   typed_chars, ai_share_pct}. Added with DEF-11, with SG + SS approval.

class Report(Strict):
    session_id: str
    mode: Mode
    overall: int
    dimensions: list[DimensionScore]
    summary: str
    strengths: list[str]
    improvements: list[str]
    moments: list[Moment]
    metrics: Metrics
    coding: CodingExtra | None
    defense: DefenseExtra | None
    model: str
    generated_at: datetime
```

### 7.6 `ws.py`: WebSocket messages

Discriminated unions on `type`. The full catalog is in §8.2.

```python
ClientMessage = Annotated[Union[Hello, EditorEvents, EditorSnapshot, CodeRun, CodeSubmit, ChatSend,
    HintRequest, PhaseAdvance, DefenseRunChaos, DefenseVerify, DefenseCircle, SessionEnd],
    Field(discriminator="type")]
ServerMessage = Annotated[Union[SessionState, InterviewerMessage, TranscriptUpdate, RunResultMsg,
    NotesUpdate, IntegrityMsg, DefenseAudit, DefenseChaosMetric, DefenseChaosDone, DefenseGrillEval,
    DefenseSamHighlight, DefenseVerdict, ReportReady, ErrorMsg], Field(discriminator="type")]
```

`export.py` builds a JSON Schema from all top-level models and unions, runs `json-schema-to-typescript`
(`pnpm dlx json-schema-to-typescript`) and writes `frontend/src/types/contracts.ts`. CI runs
`make contracts && git diff --exit-code frontend/src/types/contracts.ts`.

---

## 8. API: REST and WebSocket

### 8.1 REST (`/api`)

| Method | Path | Body → Response | Notes |
|---|---|---|---|
| GET | `/api/health` | → `{ok, version, mock}` | |
| GET | `/api/problems?difficulty=&topic=` | → `ProblemSummary[]` | |
| GET | `/api/problems/{slug}` | → `ProblemPublic` | never includes hidden tests/rubric/reference |
| GET | `/api/problems/{slug}/illustration` | → image | P1 |
| GET | `/api/defense/samples` | → `Project[]` | sample apps |
| GET | `/api/defense/projects/{id}/files` | → `ProjectSource` (path → content; never `flaws.json`, `fixed/` or `fix.patch`) | the fix-stage editor and audit file preview; samples only until uploads (P1) |
| POST | `/api/defense/projects` | multipart zip → `Project` | P1, limits §11.1 |
| POST | `/api/sessions` | `SessionConfig` → `Session` | picks a random problem if only difficulty is given |
| GET | `/api/sessions/{id}` | → `Session` | |
| POST | `/api/sessions/{id}/end` | → `Session` | starts report generation |
| GET | `/api/sessions/{id}/timeline` | → `TimelineEvent[]` | for replay. Hidden-test details never appear (nor a submit's stdout). While the session is live, also no analyses, system notes, suppressed interventions or audit details (explanations, expected points, fix steps) (§9.2) |
| GET | `/api/sessions/{id}/report` | → `Report` or 202 `{status}` | 409 `session_live` while live; 404 `report_unavailable` for a failed session. Asking restarts a report that a server restart cut short |

Errors: `{"error": {"code": str, "message": str}}` with proper HTTP status codes.

### 8.2 WebSocket `/ws/sessions/{id}` (JSON)

Client → server:

| `type` | Fields | Effect |
|---|---|---|
| `hello` | `client_now_ms` | Server replies `session.state` (includes `started_at`) |
| `editor.events` | `events: EditorEvent[]` | Sent every 500 ms when non-empty |
| `editor.snapshot` | `CodeSnapshot` | Once on attach (the baseline), every 20 changes, every 15 s with changes, and before run/submit |
| `code.run` / `code.submit` | `file`, `code` | Runs tests → `run.result` |
| `chat.send` | `text` | Text alternative to voice; becomes a candidate `TranscriptTurn` (source=text) addressed to the interviewer |
| `hint.request` | `step_id?` | Explicit hint (counted) |
| `phase.advance` | `to: Phase` | Candidate-driven transitions only: intro → clarify ("Skip intro"), clarify → coding ("Start coding") and coding → wrap_up ("I'm done"); the server rejects anything else |
| `defense.run_chaos` | `finding_id` | Normally automatic; manual retry button |
| `defense.verify` | `finding_id`, `files: {path: code}` | Re-run the attack on edited files |
| `assistant.ask` | `text`, `file: str \| None`, `selection: str \| None` | P1 (§11.9): ask the Muse fix assistant → `assistant.reply` |
| `assistant.apply` | `turn_id`, `accepted: bool` | P1: accept or reject that reply's edits (logged; accepted edits come back as an editor snapshot) |
| `defense.circle` | `finding_id`, `source: canvas\|webcam`, `image_b64` (PNG/JPEG ≤ 1 MB), `node_boxes: {node_id: [x1,y1,x2,y2]}` (canvas only) | P1: SAM 3.1 locates the circle/sketch → `defense.sam.highlight` (§11.7) |
| `session.end` | — | → ended → report |

Server → client:

| `type` | Fields |
|---|---|
| `session.state` | `session: Session`, `phase`, `remaining_s`, `interviewer_state: idle\|listening\|thinking\|speaking` |
| `interviewer.message` | `Intervention` (not sent when suppressed) |
| `transcript.update` | `TranscriptTurn` (partial and final) |
| `run.result` | `RunResult` |
| `notes.update` | `steps: StepProgress[]`, `issues: SuspectedIssue[]`, `stated_plan` (the "interviewer's notes" panel; sent after every analysis) |
| `integrity.flag` | `IntegrityFlag` |
| `defense.audit` | `AuditPublic` (findings without explanation/grill/fix rubric) |
| `defense.chaos.metric` | `ChaosMetric` |
| `defense.chaos.done` | `ChaosRun` |
| `defense.grill.eval` | `GrillTurn` + `finding: Finding`, sent once the grill for that finding is final (after the follow-up, if one is asked); the full finding is revealed only then |
| `defense.sam.highlight` | `SamHighlight` (P1) |
| `assistant.reply` | `AssistantTurn {id, t, question, answer, edits: AssistantEdit[], model}` (P1, §11.9) |
| `defense.verdict` | `Verdict` |
| `model.activity` | `ModelActivity`: a model starting or finishing work for this session, for the "Under the hood" strip (below) |
| `report.ready` | `session_id` |
| `error` | `code`, `message`, `retryable` |

**`model.activity` (the "Under the hood" strip, docs/STORY.md):**
- **Where it comes from:** the model wrapper reports each role call once when it starts and once when it ends,
  not each retry: `done` (the main model answered), `fallback` (a backup did), `failed` (every model failed),
  or `stopped` (cancelled mid-call, e.g. the engine detached at wrap-up). The hub watches the wrapper
  (`LLM.watch`) and sends calls for a session open in this process to that session's tabs. Calls without a
  session id (offline drafting) aren't shown.
- **Labels** (`engine/activity.py`): a display name per chip (never a model id) and a plain task per role:
  watching your code (analyzer), answering your question (interviewer), grading your answer (grill), reading
  your project (audit), writing an attack (attacker), writing your report (report), finding what you circled
  (vision). Muse Voice shows "listening" from speech start to the final turn, or "transcribing" per fallback
  chunk.
- **Also on the timeline** (`model_activity`), so the replay shows when each model stepped in. Never content.

**Limits** (`engine/api.py`, `engine/limits.py`, the client models in `contracts/ws.py` and `events.py`):
- **Message size:** at most 2 MiB per JSON message (the largest real one is a 1 MB circle image). Over that, the
  server sends `error{code: "too_large"}` and drops the message without parsing it.
- **Fields:** chat text ≤ 4,000 chars (the grill answer cap); a source file, code to run or a snapshot ≤ 200,000
  chars; a path ≤ 256; an editor batch ≤ 500 events of ≤ 100 changes each; step and finding ids ≤ 64; a
  `defense.verify` ≤ 60 files. Over a limit: `error{code: "bad_message"}`.
- **Rate:** 20 messages a second per socket, with a burst of 60 (real use is an editor batch every 500 ms plus the
  odd chat, run or snapshot). Messages over the rate are dropped with one `error{code: "rate_limited",
  retryable: true}` when the dropping starts. 200 drops within 10 s closes the socket with **4429**.

### 8.3 WebSocket `/ws/sessions/{id}/audio` (binary)

- The client sends **raw PCM, signed 16-bit little-endian, mono, 24 kHz**, in **80 ms frames (1,920 samples =
  3,840 bytes)** at real-time pace. Text frames: `{"type":"start"}` / `{"type":"stop"}`, and
  `{"type":"ask","holding":true|false}` when the **Ask** button is pressed and released.
- While TTS speaks, the client sends **silence** instead of the mic (not nothing): the stream keeps real-time
  pace (Meta closes streams that fall behind) and the audio clock stays aligned with session time.
- The server forwards the frames to Meta's realtime ASR (§9.7) and publishes transcripts on the JSON socket.
- Close codes: `4404` unknown session, `4403` the session has voice off, `4503` voice unavailable (no key, or
  realtime and file transcription both failed), `4409` another tab took the microphone, `4429` too many frames,
  `1000` the session ended. The browser shows "use chat" for the 44xx/45xx codes.
- **Limits:** frames over 7,680 bytes (two real frames) are dropped. 25 messages a second with a burst of 50 (twice
  real time, for network jitter); faster frames are dropped rather than forwarded, so the stream never runs ahead
  of real time. 200 drops within 10 s closes the socket with 4429.

---

## 9. Shared interviewer engine

Owner: **SG**. Used by coding mode (whole session) and defense mode (grill + fix stages).

### 9.1 SessionHub (`hub.py`)
- One `SessionRuntime` per live session in memory: config, phase, CodeState, scheduler, policy state, voice
  bridge and connected sockets. Created on the first WS connect; destroyed 10 min after the last disconnect.
- Routes client messages to handlers; every handler appends to the Timeline first, then reacts.
- `broadcast(ServerMessage)` to all sockets for the session (a second tab = observer).
- Phase transitions go through `runtime.set_phase(to, reason)`, which validates against the mode's allowed
  transitions (§10.1, §11.2), appends a `phase` event and broadcasts `session.state`. Any live phase may go
  to `ended` or `failed`; only `ReportBuilder` moves on from `ended`.
- The hub handles the shared messages (`hello`, `editor.*`, `chat.send`, `hint.request`, `phase.advance`,
  `session.end`); everything else goes to the session's **mode controller**. A runtime reopened after
  expiry rebuilds its code from the stored timeline and keeps numbering events where it left off.
- **Mode hooks** (agreed by SG and SS; `CodingController` in `coding/session.py`, `DefenseController` in
  `defense/controller.py`):
  ```python
  class ModeFactory(Protocol):                       # what the hub is given per mode (e.g. CodingMode(bank))
      async def plan_session(self, config: SessionConfig) -> SessionPlan: ...  # problem/project + time limit
      def __call__(self) -> ModeController: ...       # one controller per live session

  class ModeController(Protocol):
      def allowed_transitions(self) -> Mapping[Phase, set[Phase]]: ...
      async def on_start(self, rt: SessionRuntime) -> None: ...                  # first connect
      async def on_resume(self, rt: SessionRuntime) -> None: ...                 # runtime reopened after expiry
      async def on_client_message(self, rt, msg: ClientMessage) -> bool: ...     # False = unsupported
      async def on_timeline(self, rt, event: TimelineEvent) -> None: ...         # after every event
      async def report_extra(self, rt) -> CodingExtra | DefenseExtra: ...
  ```
  `plan_session` raises `SessionSetupError` for a bad config (→ `400 bad_config`).
  `await rt.attach(RubricContext)` / `await rt.detach()` start and stop the live engine (analyzer → policy →
  interviewer) for a rubric: coding at `clarify`, defense at `fix`. Ending a session detaches it.
  `RubricContext` is in `engine/context.py`.
  - **`on_resume`** runs on the first *connect* after a runtime is reopened, once the socket is attached, so
    what the mode says reaches the tab. Ending a session over REST doesn't resume it.
  - **`on_close(rt)`** is optional: if a controller defines it, the hub awaits it when the runtime closes, to
    cancel the mode's own timers and tasks.
  - **`rt.sender`** is the connection whose message `on_client_message` is handling, so a mode can answer just
    that tab (`rt.error(rt.sender, …)`).
  - **`say(rt, text, trigger, level, *, speak=None, step_id=None, fallback=None)`** in `engine/interviewer.py`
    sends a line the mode chose, through the leak guard (§9.6; `reference=` adds the overlap check). Coding
    uses it for phase lines; Defense can use it for grill lines.
  - **After `ended`:** `rt.end()` starts the report task (§9.8): `ended → reporting → reported`, then
    `report.ready`. `rt.last_context` keeps the last attached `RubricContext` after detach, for the report.
- Routes live in `engine/api.py` (`router`); `main.py` includes it and puts
  `SessionHub(store, {Mode.CODING: CodingMode(ProblemBank.load()), …}, model=llm)` on `app.state.hub`. Until
  `crucible.store` lands, `engine/store.py` has an in-memory `MemoryStore` with the same interface (sessions,
  events, and `save_report`/`get_report`).

### 9.2 Timeline (`timeline.py`)
- `append(kind, payload, t=None) -> TimelineEvent`: assigns `seq` (monotonic per session) and `t` (server
  time since start if not given), validates the payload against `PAYLOAD_MODELS`, writes to SQLite (batched
  every 250 ms) and keeps an in-memory tail for the analyzer. Code calls `rt.record(...)`, which appends
  and then calls the controller's `on_timeline`.
- `read(session_id, kinds=None, since_seq=0)` for reports and replay.
- `public_view(events, live=...)` is what the replay endpoint returns. `redact_run()` hides hidden cases'
  inputs and outputs (keeping the error class) and a submit's stdout, since printing the arguments would
  reveal hidden inputs. COD-3 uses the same function for `run.result`.

### 9.3 CodeState (`codestate.py`)
- Holds `code_by_file`, `version_by_file`, `last_edit_t`, `chars_typed`, `chars_pasted` and
  `code_at_last_analysis`.
- **Applying an `EditorEvent`:** sort `changes` by `range_offset` **descending**, then for each:
  `code = code[:off] + text + code[off+len:]`. (Monaco offsets refer to the model before the event; applying
  descending keeps earlier offsets valid.) Offsets are **UTF-16 units** (JavaScript strings), so Python
  converts them; an emoji counts as 2. An offset past the end clamps and reports a desync, which the next
  snapshot repairs.
- **Snapshots reconcile:** on `CodeSnapshot`, if the reconstructed code differs, trust the snapshot, log a
  `system` warning and continue.
- **Counting:** `paste` adds the inserted length to `chars_pasted`; `change` adds it to `chars_typed`;
  `undo` and `redo` count as neither (they restore earlier text). A single change inserting ≥ 80 chars
  without a paste event is a **bulk insert** (drag/drop, extension) and counts toward `chars_pasted`.
- `diff_since_analysis()` → unified diff (difflib) for the analyzer prompt; `changed_since_analysis()`
  ignores whitespace-only edits (§9.4 trigger).
- `code_at(timeline, file, t)` here and `codeAt` in `frontend/src/lib/replay.ts` implement the same
  reconstruction. A shared fixture (`backend/tests/fixtures/replay_case.json`) must produce identical code in
  both.

### 9.4 Analyzer (`analyzer.py`)

**Scheduling (single-flight per session):** run when any of the following holds, at most once every 8 s
(asks bypass the 8 s floor):
- typing paused ≥ **2.5 s** and the code changed (non-whitespace) since the last analysis;
- a `run.result` arrived;
- a final candidate transcript turn arrived (voice) or `chat.send`;
- 30 s have passed with any change.
If a call is in flight, set `dirty=True` and run once more when it returns.

**Call:** model role `analyzer` (default `muse-spark-1.3`), `reasoning_effort="minimal"`, timeout 12 s,
structured output `Analysis`, `beta.chat.completions.parse`. On timeout or error: skip this tick (no
intervention), log a `system` note, and keep the changes so the next tick looks at them again.
The analyzer depends only on a `StructuredModel` protocol (the slice of `models/llm.py` it calls), passed to
`SessionHub(model=...)`. Without a model, nothing is analyzed.

**Measured (Oct 27, quiet-streak, a buggy loop with no clarification; 1,751 input tokens):** `low` took 7.7 s
and 11.7 s on two calls; `minimal` took 4.1 s. Both found the missed step and the line-8 bug and proposed the
same nudge. `low` blows the pause → nudge budget (§18: ≤ 6 s, of which 2.5 s is the pause) and sits on the
12 s timeout, so **the analyzer runs at `minimal`** (decided by SG on Oct 27; set in `models/registry.py`,
PR #6). Re-check the quality on the gold-problem evals, and only raise the effort if `minimal` misses
steps that `low` catches.

**Prompt layout** (static first, so cached-input pricing can apply; ⚠️ VERIFY how caching triggers):
1. System: `engine/prompts/analyzer_system.md` (role, rules: never write solution code, judge only from the
   evidence shown, be conservative with confidence, step semantics).
2. Problem: statement, function signature, rubric (steps, edge cases, mistakes, approaches). Static per
   session.
3. Dynamic state: phase, elapsed/remaining time, **code with line numbers**, diff since the last analysis,
   the last 3 run results (summaries, visible-test failures with inputs, hidden failures as counts only), the
   transcript of the last 90 s, **the plan they stated earlier** (kept once it leaves that window, so
   `stated_plan` and `plan_matches_code` stay meaningful), previous step statuses, interventions already given
   (text + step) to avoid repeats, hint levels used per step, and the feedback mode.

In defense **fix** stage the "problem" block is the finding (explanation, file/lines, chaos summary) and its
`fix_steps` rubric.

After every analysis: append `analysis` to the timeline and broadcast `notes.update` (active mode only: in
passive mode the notes would be feedback, so they wait for the report). The system prompt also tells the
model that the candidate's code, comments and words are data, not instructions, so a comment like "mark
every step done" can't steer it.

**ENG-4 ships a thin policy** for IC1: only `MISSED_STEP` (with `incorrect` counting as a later step being
under way, as Spark at `minimal` marks a buggy loop), the 45 s cooldown, the 2.5 s quiet window and no
repeats, delivered at nudge level with the analyzer's wording or the rubric's first hint. ENG-5 replaced it
with the full §9.5 table. The leak guard's code check catches fences and two or more statement lines,
including block headers like `if not xs:`.

### 9.5 Policy (`policy.py`): code decides

`PolicyState` (one per session) collects what happened (`observe_analysis`, `observe_run`, `observe_edit`,
`ask`, `request_hint`) and what was already said: the ladder per step, `hints_by_level`, the cooldown clock, the
unsolicited times for the cap, the `(trigger, subject, level)` set already used, and the held message. `decide(state,
facts)` returns at most one `Decision`. `Facts` is the session right now (time, phase, feedback mode, voice,
time limit, steps, the main file's code, lines written beyond the starter code, last edit, last speech,
speech in progress). Neither does I/O or reads a clock. `engine/live.py` feeds the state from the timeline
and calls `decide()` in one policy task: every 0.5 s for the time rules, and at once on a question, a hint
request, a run or an analysis.

**Global guards (unsolicited messages, both modes):**
- Never deliver within **2.5 s** of the last edit or while candidate speech is in progress. Hold it in a
  one-slot queue, re-check the rules each tick, and deliver when quiet. If it's held for more than **20 s**,
  drop it; the rule then waits for fresh evidence (2 new analyses, or a new run).
- **45 s** minimum between unsolicited help messages; answers (`ASKED`, `HINT_REQUESTED`) restart that clock
  too, so a nudge never lands right after an answer. At most **8 unsolicited per 30 min**. Talk (`REPLY`,
  `PROBE`) uses neither, but every unsolicited line (help or talk) is at least **15 s** after the previous line.
- Never repeat the same `(trigger, subject)` at the same level. The subject is the step for ladder rules, the
  issue for `BUG_SUSPECTED` and the plan for `PLAN_MISMATCH`. `SILENT` and `IDLE` repeat on their own clocks.
- An analysis rule fires again for the same step or issue only after **2 analyses newer than its last fire**,
  so the ladder climbs on fresh evidence, not on a timer.
- `ASKED`, `HINT_REQUESTED` and `TIME_WARNING` skip these guards: they answer the candidate or tell the time.

**Rules** (evaluated in this order; the first match wins):

| Rule | Fires when | Level | Once? |
|---|---|---|---|
| `ASKED` | a `chat.send` that reads as a question: it ends in "?" or opens with a question word (`is_question`; statements typed in chat are thinking aloud) | QUESTION; a canned Socratic reply until ENG-6's `answer()` | — |
| `HINT_REQUESTED` | `hint.request` | next ladder level for the step (the requested step, else the analyzer's proposal step, else the first not-done required step) | — |
| `TIME_WARNING` | 50% and 80% of the time limit elapsed | INFO, text only | each once (both at once give one) |
| `PASTE` | paste ≥ 40 chars or ≥ 2 non-blank lines, or a bulk insert (≥ 80 chars in one change) | INFO, text only, neutral ("I noticed a pasted block. I'll focus my feedback on the parts you wrote.") | said once; COD-4 logs every flag |
| `CODED_BEFORE_PLAN` (P1) | ≥ 3 non-blank lines written beyond the starter code (the editor's first snapshot) while no plan has been stated this session (the policy keeps the latest `stated_plan`, so a plan older than the analyzer's 90 s window still counts), voice on, in `clarify`/`coding` | QUESTION ("Before you go further, what's your approach?") | once |
| `RUN_FAILED` | the same visible test failed on 2 runs in a row, or 1 failure then 30 s with no edit or speech (hidden tests never count) | ladder for the step: the analyzer's `RUN_FAILED` step, else the first `incorrect` step, else the first required step not done | — |
| `MISSED_STEP` | a required step is `skipped`/`not_started` while a step with higher `order` is `in_progress`/`done`/`incorrect`, seen in **2 consecutive analyses**; waits while the analyzer's own proposal for it is below 0.7 | QUESTION, asked once per step: the interviewer tests, it doesn't hint. HINT and CONCEPT only when the candidate asks (`HINT_REQUESTED`) or is stuck (`RUN_FAILED`) | per step |
| `BUG_SUSPECTED` | a `bug` or `edge_case` issue with a line and confidence ≥ 0.75, seen in 2 consecutive analyses, its line's text unchanged for 20 s | NUDGE, canned "Take another look around line N" (never the analyzer's draft, which may hint at the fix) | per issue |
| `PLAN_MISMATCH` (P1) | `plan_matches_code == false` in 2 consecutive analyses, with a stated plan (the latest, or the one the policy remembers) | QUESTION | per plan |
| `SILENT` (P1, voice on) | in `coding`, ≥ 75 s without a final candidate turn (voice or chat) | NUDGE, a check-in the model words from the screen (`reply(kind="checkin")`), canned "Talk me through what you're doing." | every 3 min max |
| `IDLE` | in `coding` (or defense `fix`), no edit and no speech ≥ 60 s | QUESTION, a model-worded check-in, canned "Where are you at?" | every 2 min max |
| `REPLY` (talk, active) | in `clarify`/`coding`, the candidate said or typed something that isn't a question (≥ 6 words; a voice turn the classifier labels thinking aloud), the interviewer has been quiet ≥ 20 s (counting from the problem's presentation), within 8 s of it being said. It goes out as soon as it's written: the final transcript already ended their turn, so it skips the quiet window unless they talk or type again | INFO: the model (`reply(kind="reply")`) asks one follow-up that makes them justify it, or acknowledges briefly; never confirms or hints | 1 per 40 s, 12 per session |
| `PROBE` (talk, active) | in `coding`, a step became `done` that wasn't probed yet, no serious issue open, quiet ≥ 45 s. Code decides when; the model (`reply(kind="probe")`, never shown the rubric) asks why their code works, what a line does for an input, or what a part costs | QUESTION | 4 per session; steps done together get one probe |
| `PRAISE` | a step marked tricky in the rubric becomes `done` | INFO | max 1 per 10 min |

**Response time (Oct 28).** A real run felt slow (3–4 s), so the engine doesn't make the candidate wait for
steps in a row: on a final spoken turn it starts writing the answer and, if a reply could go out, the reply
while the classifier decides which it is, then sends the one that fits (`LiveEngine._write_ahead`). The warm-up
reply is written during the pause after an answer. Measured before: thinking aloud → reply 3.6 s after the
final transcript (classifier 0.6 s, quiet window 1.5 s, model 1.3 s); question → answer 2.0 s; warm-up 4.4 s.

**Talk vs help (built Oct 28).** `REPLY`, `PROBE` and the check-ins are the interviewer's side of the
conversation, not help: they don't count as interventions shown or against independence (`NOT_HELP`), and the
model writes them on delivery with the `conversation` role (Spark low, 6 s; the strip says "talking with you"),
falling back to canned lines. They're active-mode only.

`PRAISE` isn't built: `RubricStep` has no "tricky" flag, so it needs a contract change (SG + SS). It's a
`TODO(ENG-5)` in `policy.py`.

**Hint ladder:** `ladder[step]` advances 0→1→2→3 each time a ladder rule (`HINT_REQUESTED`, `RUN_FAILED`,
`MISSED_STEP`) is shown for that step: `1 = nudge` (rubric `hints[0]`: point at the area), `2 = question`
(`hints[1]`: Socratic), `3 = hint` (`hints[2]`: names the technique), and beyond that `concept` (explain the
idea in general terms, no code; a canned line until ENG-6 phrases it). The LLM may rephrase the rubric hint
to fit the candidate's code but must stay at the level. Every shown ladder message counts toward
`hints_by_level` (independence score); suppressed ones don't.

**Text** (`interviewer.deliver`): the analyzer's draft when its proposal matches the trigger, step and level
(for `HINT_REQUESTED`, any trigger); else the rubric hint for a ladder rule; else the trigger's canned line
from `engine/prompts/canned.md`. Every text passes the leak guard's code check; on a hit it falls back to the
rubric or canned text, then to a generic line. `PASTE` and `TIME_WARNING` are text only (`speak=False`).

**Passive mode:** every rule is still evaluated, through the same guards, and logged as
`Intervention(suppressed=True)`, so the log matches what active mode would have shown. Suppressed messages
don't climb the ladder. Only `ASKED`, `HINT_REQUESTED` and `TIME_WARNING` are delivered.

**Wiring:** the hub routes `hint.request` to `LiveEngine.request_hint` (an `unsupported` error when no live
interviewer is attached, e.g. without a model). Partial transcripts aren't stored (§9.7), so ENG-7's
VoiceBridge calls `LiveEngine.heard_speech()` to hold messages while the candidate talks.

**Tests:** `tests/engine/test_policy.py` drives `decide()` with synthetic `Analysis` sequences, runs, edits
and clocks: a "fires" and a "doesn't fire" test per rule, and a test per guard (cooldown, cap, no repeat,
quiet window and hold, stale drop), the ladder and passive mode. `tests/engine/test_live.py` covers the
wiring; `test_first_nudge.py` runs the hint button end to end.

### 9.6 Interviewer (`interviewer.py`)
- **Nudges, questions and hints** (`deliver(rt, decision, context)`): the analyzer's draft when the policy kept it,
  else the rubric hint for the step and level, else the trigger's canned line (`prompts/canned.md`). No extra
  model call to phrase them: the analyzer already drafts at the right level, and a second Spark call would add
  2–6 s to every nudge.
- `answer(rt, model, context, question) -> str | None`: replies to `ASKED` with one Spark call (role
  `interviewer`, prompt `prompts/interviewer_answer.md`, 15 s deadline covering the wrapper's 6 s timeout and
  retry). The model sees only what the candidate can see: the statement, signature, examples and constraints
  (`RubricContext.brief_md`), their numbered code, the last 8 final transcript turns within 3 min, and the
  question. Never the rubric, hidden tests or reference. It answers clarifying questions from the spec (or
  says to state an assumption), answers "is this right?" with a question, and never confirms correctness. A
  leaky reply gets one retry asking for a Socratic question; a second leak, a timeout or a model error sends
  the canned `asked` line, with a `system` note.
- Phase lines: intro (problem presentation, ≤ 60 words), wrap-up questions (from `rubric.wrap_up_questions`),
  closing line. They are canned templates (`coding/prompts/phase_lines.md`), so the intro plays as soon as
  the candidate joins and can't leak.
- **Leak guard** (`leak_reason(text, reference)`, applies to every outgoing text): reject it if it contains a
  code fence or ≥ 2 lines that parse as Python statements, or if any line of it (or the whole text) shares
  ≥ 60% of the tokens of a non-trivial reference line. Non-trivial means ≥ 5 tokens and not a signature,
  comment, docstring or import. The reference is the problem's reference solution (or a sample's fix). On
  rejection in `deliver()`: send the rubric hint or canned line instead, else a generic prompt to walk through
  the code. In `answer()`: retry once, then the canned line. Every rejection is logged and noted on the
  timeline.
- `say(rt, text, trigger, level, *, speak=None, step_id=None, fallback=None, reference=None)`: the entry point
  other modes use (Defense grill questions, feedback and follow-ups, coding phase lines). It runs the same leak
  guard, checking overlap against `reference` when given. On rejection it sends the caller's `fallback` text
  (Defense passes a canned Socratic question) instead of a rubric hint, which grill messages don't have. With
  no fallback it sends the canned line for the trigger.
- Speech: `speak = config.speak_replies`, except PASTE and TIME_WARNING notes, which are text-only. The browser speaks
  it; the backend appends an interviewer `TranscriptTurn` (source=text) so the replay shows it.

### 9.7 VoiceBridge (`voice.py`)
One `VoiceBridge` per session (`rt.voice`), opened by the audio socket; `models/asr.py` talks to Meta (V1).
- **Realtime:** on `start`, open `wss://api.meta.ai/v1/asr/realtime` and send the handshake as the first text
  frame (10 s limit): `{"authorization": {"accessToken": "Bearer <MODEL_API_KEY>"}, "model":
  "muse-voice-transcribe-1.0", "audioEncoding": "PCM_24KHZ", "mode": "ENDPOINTING", "partialMode":
  "CUMULATIVE", "emitAudioProgress": false, "languageBias": ["English"]}`. The acknowledgement is
  `{"sessionId"}`, the only frame without `type`.
- Forward binary frames as they arrive. Audio that arrives while (re)connecting is dropped, never buffered and
  burst (Meta closes with 1008 when a stream runs ahead of real time).
- **ENDPOINTING events:** `speechStart{turnId}` → cumulative `transcript` partials (no `turnId`: they belong to
  the latest `speechStart`) → `speechEnd{turnId}` → `speechComplete{turnId, transcript}` with the final text.
  Every event carries `audioProcessedMs`; there are no `startMs`/`endMs` in realtime. A turn's session times are
  `t0 + audioProcessedMs` of its `speechStart` and `speechEnd`, where `t0` is the session time the stream's first
  frame began. Partials → `transcript.update` (final=false, not stored); `speechComplete` → a final
  `TranscriptTurn(source="voice")` on the timeline, then `transcript.update`. Speech in progress holds unsolicited
  messages (`rt.heard_speech()`) and sets `interviewer_state` to `listening`.
- **Is the candidate talking to the interviewer?** P0: a `chat.send` that reads as a question
  (`policy.is_question`), or a voice turn spoken while **Ask** was held for at least half of it (any overlap
  isn't enough: candidates let go and keep talking, and turn times can be a few hundred ms off). Questions asked
  before the reply are answered together (a spoken question often arrives as two turns). **Built (COD-6):**
  every other final spoken turn goes to a cheap classifier (`engine/classifier.py`, `prompts/classifier.md`,
  Spark `minimal`, 3 s, output `TurnLabel`) in a background task, with the candidate's 3 earlier spoken turns as
  context. `question_to_interviewer` → ASKED. A turn is asked at most once (Ask and the classifier can both flag
  it). A failure counts as thinking aloud, with a `system` note, because interrupting someone who is thinking is
  worse than a missed question. Typed chat still uses `policy.is_question`. Wrap-up and grill answers are never
  classified (the engine is detached then).
- **Close codes:** `1000` done (after our `endStream`; otherwise reconnect). `1011` → reconnect with backoff
  (0.5 s, doubling); at "Max session duration reached" (the 60-min cap) reconnect without counting a failure.
  `1013` → wait 5 s, then reconnect. `1008` (bad request or streaming policy) → straight to the chunked fallback,
  since retrying the same stream fails again. On `stop`, send `{"type":"endStream"}` and read up to 5 s for the
  last turns.
- **Fallbacks:** after 3 realtime failures in a row, transcribe 10 s WAV chunks with `POST /v1/asr/transcribe`
  (multipart `request` = `{"model", "audioEncoding": "WAV", "mode": "ENDPOINTING"}` + `audio`), which returns
  `turns[{startMs, endMs, transcript}]` relative to the chunk. On `stop`, a last chunk of ≥ 1 s is sent. If two
  chunks fail in a row, voice is unavailable: a `system` note, an `error{code: "voice_unavailable"}` on the JSON
  socket ("use chat"), and the audio socket closes with 4503. Word timestamps aren't available (turn-level
  only), so speaking pace is computed per turn.

### 9.8 ReportBuilder (`report.py`)
1. **Metrics in code** from the stored timeline (`Metrics`, §7.5). Interventions shown and `hints_by_level`
   count only help the candidate saw: not suppressed ones, phase lines, grill questions, or paste and time
   notes. Talk time is voice turns only. The longest silence is the longest stretch with no talking, typing or
   runs, counted only in phases where the candidate is expected to act (clarify, coding, wrap-up, grill, fix).
2. **Candidate moments in code** (up to 14, sorted by `t`; a short session has fewer): first edit, approach
   stated, each intervention shown (with "time to recover": when its step next became `done`), questions the
   candidate asked, first passing run, each integrity flag, the longest silence (≥ 60 s), the final submit,
   wrap-up answers; defense: each chaos verdict, grill score and verify result, and the verdict. Over 14, the
   most important kinds are kept (submit, verdicts, broken findings, first edit first).
3. **ReportDraft** from model role `report` (`muse-wonder-1.0`, `reasoning_effort="high"`, timeout 45 s →
   Spark 1.3, same schema) via `complete_json_with_model`, which also returns the model that answered. Prompt:
   `engine/prompts/report_system.md`, with the problem and rubric (or findings, chaos runs, grill and verdict),
   final code, step history, runs, transcript, interventions, metrics and candidate moments. Overall deadline
   100 s. No model, a failure or the deadline → a **template report** from metrics only (`model: "template"`,
   with a `system` note).
4. **Merge, code decides:** scores code can measure replace the model's: coding `correctness` = hidden tests
   passed (of the last submit); defense `correctness` = broken findings that held after the fix, and
   `system_understanding` = the average grill score. Dimensions are kept in the mode's order (coding:
   problem_solving, correctness, code_quality, communication, independence, debugging; defense:
   system_understanding, debugging, correctness, communication, independence). `overall` = the mean of the
   dimension scores × 10. Moments: one per candidate moment, with code's `t` and `kind` and the model's words
   (the facts as they are when the model skipped one). Three strengths and improvements at most.
   The template report scores `correctness` from the last run when there was no submit, and `independence` as
   10 − (1 per nudge, 1.5 per question, 2.5 per hint, 4 per concept).
5. **Store** it, set phase `reported` and broadcast `report.ready`. A bug in the builder sets `failed` with a
   `system` note instead of leaving the session in `reporting`.
Score guidance in the prompt: independence falls with hint levels used; communication uses explanation quality
and talk time, and never penalizes missing voice when voice was off; correctness uses hidden-test results.

---

## 10. Mode A: Live Coding Interview

Owner: **SG**. Data: **ST**.

### 10.1 Phases and timers
`setup → intro → clarify → coding → wrap_up → ended → reporting → reported`
- `intro → clarify`: after the warm-up (2 answers, 90 s, 25 s with no answer, or "Skip intro"). The clock
  doesn't run during the intro: leaving it adds the elapsed time to `time_limit_s`.
- **Warm-up (built Oct 28):** a greeting that asks about the candidate (`WARMUP`, QUESTION); the model
  (`interviewer.reply()`, prompt `interviewer_warmup.md`, never shown the problem) reacts with one follow-up,
  then a closing line; then the problem. Spoken answers wait for the quiet gap, like wrap-up answers. Canned
  lines when the model fails. `CodingMode(warm_up=False)` goes straight to the problem (engine tests, evals).
- `clarify → coding`: the candidate clicks **Start coding** (`phase.advance`) or makes the first substantive
  edit (≥ 3 non-blank lines).
- `coding → wrap_up`: on a submit that passes all hidden tests, when time runs out, or on the candidate's
  "I'm done".
- `wrap_up → ended`: after both wrap-up answers (or 3 min).
- Time limits: easy 20 min, medium 30, hard 40 (`time_limit_min` in the problem overrides). **Demo preset:**
  10 min.
- **As built (COD-2, `coding/session.py`):**
  - **Intro:** the interviewer says a phase line from `coding/prompts/phase_lines.md` (problem title, minutes)
    through `say()`, then moves straight to `clarify` and attaches the rubric. ENG-6 keeps it canned rather
    than model-phrased, so it plays at once.
  - **"Started coding"** = 3 new non-blank lines compared with the starter code, typed or pasted. Programmatic
    snapshots don't count.
  - **Time limit:** a 0.5 s timer moves `clarify` or `coding` to `wrap_up` when `remaining_s` reaches 0.
    `clarify → wrap_up` is allowed only for this.
  - **Wrap-up:** entered for any of three reasons, each with its own opener line ("passes every test",
    "That's time", or a plain one for "I'm done"). The live engine is detached, so chat answers aren't treated
    as questions. The rubric's `wrap_up_questions` are asked one per candidate answer, then the closing line,
    and the session ends. With no answer for 3 min (`wrap_up_limit_s`), it closes anyway.
  - **When an answer is over:** a typed answer moves on at once. A spoken one moves on after **1.2 s** with no
    new candidate speech (`ANSWER_GAP_MS`; 2.5 s felt slow in a real run, Oct 28): Muse Voice ends a turn at
    every pause, so "It's O of n time" [pause] "and O of one space" arrives as two final turns. Each new final
    turn restarts the wait, and a turn still being spoken (speechStart has set the interviewer state to
    `listening` and the turn isn't final yet) holds it. A typed answer while a spoken one is waiting moves on at
    once and drops the wait. Two answers to the same question move on once. The 3-minute limit still closes the
    session, even mid-sentence. Live check (real Muse Voice, two clips 1.5 s apart with silence streaming
    between): one next question, 2.5 s after the second half's final turn.
  - **Resuming during the wrap-up** recounts the questions already asked from the timeline and waits for the
    next answer.
  - Phase lines show in passive mode too: they run the interview, they aren't feedback.

### 10.2 ProblemBank (`problems.py`)
- Loads `data/problems/*/problem.json` (+ `statement.md`, `reference.py`, `brute.py`) at startup and
  validates against `ProblemSpec`. An invalid problem fails startup in dev and is skipped (with a log) in prod
  (`ProblemBank.load(root, strict=...)`). Folders starting with `_` are drafts, and the slug must match its
  folder. The loader and `pick(difficulty, topic)` landed with ENG-4, which needs a rubric to attach.
- `random(difficulty, topic)` excludes problems used in the last 5 sessions from the same IP (best effort).
  Not built yet: `pick()` is uniform among matches.
- `CodingMode(bank, runner=...)` is coding's mode factory: an explicit `problem_slug` must exist, otherwise a
  problem is picked at the difficulty and topic, and the problem's `time_limit_min` sets the session limit.
  `runner` may be a factory (`main.py` passes `lambda: make_runner(settings)`), so a misconfigured runner
  surfaces as an error on Run, not at startup.
- **API** (`coding/api.py`): `GET /api/problems?difficulty=&topic=` → `ProblemSummary[]` (sorted by slug) and
  `GET /api/problems/{slug}` → `ProblemPublic` (404 `problem_not_found`). `main.py` shares one `ProblemBank`
  between the hub and this router (`app.state.problems`).

### 10.3 Tests (`tests.py`)
- **Run** = visible tests; **Submit** = visible + hidden. Calls `Runner.run_tests` (§12) with code,
  function signature, cases and limits (2 s per test, 10 s total), with a 20 s outer deadline.
- Hidden test inputs/outputs never leave the backend: the browser gets pass/fail + error class only.
- Results → timeline `run` → `run.result` → analyzer trigger.
- Built in COD-3 as `RunService`: one run at a time per session (a second press gets a retryable `busy`). If
  the code sent with Run differs from the tracked code, it's recorded as a snapshot first, so the replay shows
  exactly what ran. The full result goes on the timeline and the browser gets `redact_run()` (§9.2). A runner
  failure leaves a `system` note and sends `runner_unavailable` (retryable) to the tab that pressed Run, via
  `rt.sender` (the connection whose message the mode is handling). Run works from `clarify` on; a submit that
  passes every test during `coding` moves to `wrap_up` (§10.1).
- The Modal runner's `run_tests` is RUN-2. Until then, coding sessions need `RUNNER=local` +
  `ALLOW_LOCAL_RUNNER=1` (dev).

### 10.4 Integrity (`integrity.py`)
- Editor `paste` with ≥ 40 chars or ≥ 2 lines → `IntegrityFlag(kind="paste")`.
- A single change ≥ 80 chars without a paste event → `bulk_insert`.
- `hidden` → `visible` lasting ≥ 10 s → `tab_hidden` with the duration.
- P2 proctor mode: §10.6.
- Copy in the UI and the report is neutral: "pasted 32 lines at 06:14".
- **As built (COD-4):** `IntegrityDetector` turns editor events into flags. Each flag is recorded as an
  `integrity` timeline event and sent as `integrity.flag`. The wording is factual only: "pasted 2 lines at
  06:14", "120 characters appeared at once at 03:02", "switched away for 14 s at 08:40" (a tab-away flag carries
  the time it started). The policy's `PASTE` rule (ENG-5) still decides whether the interviewer mentions a
  paste; the flags are the record.

### 10.5 Coding report extras
Final step statuses, chosen approach, whether the complexity answer matched an acceptable approach.

- **As built (COD-5):** at report time, `coding/complexity.py` takes what the candidate said after the wrap-up
  question that mentions "complexity", up to the next question (a spoken turn that started before the next question
  still counts). Role `complexity` (Spark low, 8 s, prompt `coding/prompts/complexity.md`) writes down only the
  stated bounds as a `ComplexityClaim`, in the rubric's variable names; it is shown the rubric's approach names
  and bounds, never which are acceptable. Code decides: `complexity_answer_ok` is true when the stated time bound,
  and the space bound if one was given, match one acceptable approach up to notation (`O(nm log(m))` is
  `O(n * m log m)`; constants and dominated terms drop), leaving out an added term is allowed (`O(n)` for
  `O(n + r)`), and a missing or wrong time bound is false. Not asked, not answered or no model → null; a failed
  call → null with a system note. The report model is told the verdict and approach so the review agrees.
  On real Spark: 29 of 30 phrasings across the three gold problems graded as expected, p50 1.7 s (the miss
  was two connect timeouts in a row; the 20 s guard now covers the wrapper's retry).

### 10.6 P2: SAM 3.1 features (`vision/`)
- **Show your work:** the candidate clicks "Show sketch", holds paper up to the webcam, and the browser
  captures one JPEG → backend → SAM 3.1 (`POST /v1/responses`, `model: "sam-3.1"`, content: `input_text`
  `"sheet of paper"` + `input_image` as a base64 data URL; stream it) → parse the first box
  `<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|>` → crop → Muse Spark (image input) reads the sketch → a candidate
  `TranscriptTurn(source="text", text="[sketch] …")` → analyzer. Only the box is needed; ignore mask payloads.
- **Proctor (opt-in, `config.proctor`):** one frame every 15 s → SAM prompts `"cell phone"` and `"person"` →
  `phone_in_frame` / `extra_person` flags. Frames aren't stored.

---

## 11. Mode B: Project Defense

Owner: **SS**. Data (sample apps): **ST** with SS reviewing.

### 11.1 Project constraints
- Python 3.12 web app (FastAPI or Flask), with `requirements.txt` and in-memory or SQLite state only (no
  external services).
- ≤ 60 files, ≤ 6,000 lines, ≤ 2 MB zipped; ignore `.git`, `venv`, `node_modules`, `__pycache__`.
- Entrypoint: `crucible.json` `{"entrypoint": "...", "port": 8080}`; otherwise auto-detect a FastAPI
  `app = FastAPI()` in `main.py`/`app.py`/`app/main.py`. LocalRunner may remap the port to a free one.

### 11.2 Phases
`setup → audit → chaos → grill → fix → verify → verdict → ended → reporting → reported`
- `chaos` loops over queued findings; `grill` loops over findings with verdict `broke`; `fix` covers all broken
  findings in one editor session (tabs per file); `verify` re-runs every baseline script.
- If verify fails, return to `fix` (max 2 extra rounds, then verdict).
- `defense/controller.py` (`DefenseController`, implementing SG's `ModeController` hook, the defense twin of
  `CodingController` in `coding/session.py`) drives this sequence through `runtime.set_phase()`. Grill
  questions go out through `Interviewer.say()`; the fix stage attaches a `RubricContext` built from the
  finding. Ingest happens in `setup` (`projects.py`), before the session starts.
- The phase enum is the shared `Phase` (§7.1); there is no separate defense enum. Outcomes such as "chaos
  broke it" or "merge approved" are data (`ChaosRun.verdict`, `Verdict.passed`), not phases. The UI's stage
  labels (Auditing → Chaos run → Broke → Grill → Fixing → Verifying → Merge approved/rejected) are derived
  from phase + latest data by a selector in `frontend/src/lib/defense.ts` (SS).

### 11.3 Audit (`audit.py`)
- Model role `audit` (default `muse-wonder-1.0`, `reasoning_effort="high"`, timeout 120 s). Input: the file
  tree + every file with line numbers, plus `prompts/audit_system.md` (categories, "only report flaws a load
  test or a short explanation can demonstrate", max 5 findings, each with a chaos plan when testable, grill
  spec, fix_steps rubric with 2–4 steps and 3 hints each). Prompt rules that the grill depends on: titles
  and the summary name the area but never the cause or the fix; `expected_points[0]` is the root cause;
  every finding's `node_id` points at an existing node.
- Code checks after the call: every `node_id` exists (else set it to `None`), nodes with findings get
  `flagged = true`, and the browser receives `AuditPublic` only (§8.2).
- Output `AuditResult`. Cache by `content_hash` in the `audits` table (sample apps audit once).
- Fallback: Spark 1.3 with the same schema. For sample apps, if both fail, fall back to `flaws.json`
  converted to findings (and log it; never present it as an AI result in the demo).
- **Eval:** for every sample app, the audit must report each seeded flaw (same file, overlapping lines,
  same category). Recall is tracked in `make evals`.

### 11.4 Chaos lab (`chaos.py`, `attack_writer.py`, `validator.py`)

**Template** (`runner/harness/chaos_template.py`, owned by code). The model writes only three function bodies:

```python
import asyncio, json, math, random, string, time, uuid
import httpx

BASE = "http://127.0.0.1:{port}"
CONCURRENCY = {concurrency}
DURATION_S = {duration_s}

async def setup(client: httpx.AsyncClient) -> dict:
{setup_body}

async def make_request(client: httpx.AsyncClient, i: int, ctx: dict) -> httpx.Response:
{request_body}

async def check_invariant(client: httpx.AsyncClient, ctx: dict) -> tuple[bool, int, str]:
{invariant_body}

# --- fixed runner below: workers, latency histogram, JSON-lines metrics every 500 ms ---
# emits {"t_ms", "in_flight", "rps", "p50_ms", "p95_ms", "p99_ms", "errors", "violations"} lines, then
# {"done": true, "invariant_ok": bool, "violations": int, "detail": str, "requests", "errors", "p95_ms", "p99_ms"}
# check_invariant returns (ok, violations, detail): violations is a count people understand (dollars missing,
# seats double-booked), shown live; detail is the headline ("$1,240 disappeared"). The template also runs it
# every 0.5 s on its own small client, and spreads the attack across several connection pools: one httpx
# pool collapses under ~50+ concurrent requests and would make a fixed app look broken.
```

**AttackWriter:** model role `attacker` (`muse-spark-1.3`; for sample apps, the reference attack is the last
fallback) → `AttackFunctions`. Input: the finding, its chaos plan, the relevant source files and the
template.

**ScriptValidator** (AST, before any execution):
- Allowed imports: the ones in the template only. Rejected names/attributes: `open`, `exec`, `eval`,
  `compile`, `__import__`, `globals`, `locals`, `getattr`, `setattr`, `os`, `sys`, `subprocess`, `socket`,
  `pathlib`, `shutil`.
- Every string literal that looks like a URL must start with `/` or `BASE`.
- `CONCURRENCY ≤ 200`, `DURATION_S ≤ 30`.
- On rejection: one regeneration with the validator's error message, then fail the finding (`error`).
- Also rejected (PR #15 review): asyncio/loop escape hatches by attribute name (`create_subprocess_*`,
  `open_connection`, `start_server`, `to_thread`, `run_in_executor`, `get_*event_loop`, ...), any private
  attribute (`client._transport`), and direct use of `httpx` (the bodies must use the `client` they're given).
- **Containment in layers:** the validator checks the code; the template's clients carry a request hook that
  refuses any host but loopback, which catches URLs built at runtime; and Modal sandboxes run with
  `block_network=True`, so nothing leaves even if both checks miss something.
- The model never writes a whole script: the template owns imports, concurrency, timing and the metric
  output, so every metric line matches `ChaosMetric` by construction.

**Execution:** `Runner.start_project(project_files, entrypoint, port)` → readiness probe on the port →
`exec("python", "/work/attack.py")`, streaming stdout. Each metric line → `ChaosMetric` → timeline +
`defense.chaos.metric`. The final line sets the verdict: `broke` if `invariant_ok == false`, errors > 5% or
`p95_ms > plan.p95_threshold_ms` (when set); `held` otherwise; `error` on a crash or timeout (60 s hard cap).

**P1 agent loop:** if the baseline `held` but the finding claims it should break, give the model the metrics
and detail and ask for a revised attack (max 2 refinements). A plain call per refinement is enough.

### 11.5 Grill (`grill.py`)
- For each `broke` finding: the question = `grill.question` rewritten with the real chaos summary (Spark,
  timeout 6 s; fallback: the raw question + summary).
- Answer window 90 s (voice turns or chat). Then `GrillEval` (Spark, structured). If `needs_follow_up` and no
  follow-up has been asked yet: ask `grill.follow_up` (60 s more). Code enforces at most one follow-up.
- **Scoring is code, not the model** (the LLM only says which expected points were hit):
  ```python
  n = len(spec.expected_points)
  hits = {i for i in eval.points_hit if 0 <= i < n}   # indexes the model invents are ignored
  root_cause_hit = 0 in hits
  score = round(10 * len(hits) / n)                   # Python rounds .5 to even (5/2 points → 5)
  if sam_node_id is not None and sam_node_id == finding.node_id:
      score = min(10, score + 1)          # P1 bonus for locating the flaw on the diagram
  ```
  The bonus can't stand in for the root cause: the verdict (§11.6) requires `root_cause_hit` regardless.
- `eval.feedback` and any follow-up text go through the leak guard (§9.6) like every interviewer message.
- Append a `GrillTurn` to the timeline → `defense.grill.eval` (with the full `Finding`, now revealed).

### 11.6 Fix, verify, verdict (`verify.py`, `verdict.py`)
- Fix: the room opens the finding files. The engine (§9) runs with the finding as the "problem" and
  `fix_steps` as the rubric. Same analyzer, policy, ladder and leak guard (the leak guard compares against the
  sample's `fix.patch` when one exists).
- Verify: `defense.verify` with the edited files → the same baseline script re-runs against them →
  `ChaosRun(kind="verify")`.
- Verdict: `passed = all verify runs held and avg_grill_score >= 6 and every grilled finding has
  root_cause_hit`. Reasons list what failed, with the before/after numbers ("violations 37 → 0").
- P2: a "suggested refactor" for unfixed, lower-severity findings: Wonder produces a unified diff shown in
  the report ("apply with Muse Code"). Only if Muse Code's headless mode is confirmed (§23).

### 11.7 P1: "Circle the flaw" with SAM 3.1 (`grill.py` + `models/sam.py`)
- During the grill the candidate can draw a rough circle on the topology diagram (or hold a paper sketch up
  to the webcam). The browser sends `defense.circle` with a PNG of the canvas (plus each node's box in
  canvas pixels) or a webcam JPEG.
- Backend → SAM 3.1 (`POST /v1/responses`, `model: "sam-3.1"`, `input_text` `"hand-drawn circle"` for the
  canvas or `"sheet of paper"` for the webcam, + `input_image` as a base64 data URL; timeout 5 s) → first
  box (§10.6 parsing; ⚠️ VERIFY V9).
- **Code** picks the node: the node box with the largest intersection-over-node-area with the SAM box
  (≥ 0.3, else `None`). Webcam sketches go through §10.6's crop + Spark read instead and only add a
  `[sketch]` transcript turn.
- Append `SamHighlight` to the timeline → `defense.sam.highlight` (the UI pulses that node). The node feeds
  the +1 grill bonus (§11.5). On SAM failure: no highlight, no bonus, grill continues.
- Why SAM and not the stroke points: the same path serves the paper sketch, and it's a genuine use of
  SAM's text-prompted segmentation rather than a geometry shortcut.

### 11.8 P2: Merge-gate card (`card.py` + `models/image.py`)
- After the verdict, generate one `muse-image-1.0` background (`/v1/images/generations`, no text in the
  prompt, because image models garble text; timeout 20 s) and compose the real numbers (app, violations
  before → after, p99 before → after, PASS/FAIL) on top in HTML/SVG. Stored as `DefenseExtra.card_url`.
- Runs in the background after `defense.verdict`; never blocks the verdict or the report.

### 11.9 P1: Muse fix assistant (`defense/assistant.py`, DEF-11)
A Muse Spark coding assistant in a side panel during **fix** (and verify), the way people really work with AI.
The grill comes first, so the candidate has already explained the flaw without help before the assistant
appears. **Everything it does is on the timeline and in the report**, so the result shows how much of the fix
the AI wrote.
- **Ask:** the candidate types a question, optionally with a selected range (`assistant.ask`). The assistant
  sees the full finding (revealed after the grill), the project files with their current edits, the chaos
  summary and the latest verify result. It answers in prose and may propose **edits** (`AssistantEdit`: a
  file and its new contents), which the panel shows as a diff (`assistant.reply`).
- **Apply:** the candidate accepts or rejects each reply's edits (`assistant.apply`). Accepted edits go
  into the editor through the capture lib's `programmatic()` path. CodeState counts them as **AI-written**
  (`chars_ai`), not as typed or pasted, so they never raise an integrity flag.
- **Not the interviewer:** the leak guard (§9.6) doesn't apply to assistant replies, because the candidate
  asked for code. The interviewer still never volunteers the fix, and the analyzer keeps watching the editor.
- **Merge gate unchanged:** the same attack must hold and the grill must pass. The verdict reasons and the
  report add the AI share ("38% of the changed lines came from the assistant; 3 of 4 suggestions accepted"),
  and independence scoring (§9.8) accounts for it.
- **Limits:** only in fix/verify, at most 20 asks per session (cost guard, about $0.002 each). Timeout 20 s;
  on failure the panel says the assistant is unavailable and the session continues.

---

## 12. Runner

Owner: **SS**. Shared by both modes.

```python
class Runner(Protocol):
    async def open_session(self, session_id: str) -> None: ...          # warm sandbox (coding)
    async def run_tests(self, session_id: str, req: RunRequest) -> RunResult: ...
    async def start_project(self, project: Project, files: dict[str, str]) -> ProjectHandle: ...
    def stream_exec(self, h: ProjectHandle, argv: list[str], timeout_s: int) -> AsyncIterator[str]: ...
    async def stop_project(self, h: ProjectHandle) -> None: ...
    async def close_session(self, session_id: str) -> None: ...
```

The request and handle types live in `runner/base.py`. They're backend-internal (never sent over the
WebSocket), so they aren't in `contracts/`:

```python
class RunLimits(Strict):
    per_test_s: float = 2.0
    total_s: float = 10.0
    stdout_bytes: int = 4096

class RunRequest(Strict):
    run_id: str
    t: int                        # session time when Run/Submit was pressed
    kind: Literal["run", "submit"]
    code: str
    function: FunctionSig
    cases: list[CaseSpec]         # run: visible only; submit: visible + hidden
    hidden_case_ids: list[str] = []  # sets CaseResult.visible (redaction stays the caller's job)
    limits: RunLimits = RunLimits()

@dataclass
class ProjectHandle:
    project_id: str
    port: int
    sandbox_id: str | None        # Modal sandbox id; None for LocalRunner
    workdir: str | None           # LocalRunner temp dir; None for Modal
```

`run_tests` sends the harness `{code, function, cases, limits}`, then adds `run_id`, `t` and `kind` from the
request to the harness output to return a full `RunResult`. Hiding hidden-test details from the browser is
the caller's job (`coding/tests.py`, §10.3), not the runner's.

- **Harness** `runner/harness/run_tests.py`: reads one JSON object from **stdin**
  `{code, function, cases, limits}`, executes the code in a fresh module namespace, runs each case in a
  subprocess-free loop with `signal.alarm`-based per-test timeouts, compares with the comparator
  (`exact`, `unordered`, `float_tol` 1e-6, `unordered_inner`, `set_of_lists`), captures stdout (4 KB cap), and
  prints one JSON `RunResult` body. Syntax errors → `compile_error`.
- **ModalRunner:** (verified on real Modal 2026-10-27: the image builds, files are written with `exec` + stdin, a
  readiness probe on the port works, and the bank race reproduces. Modal's stdout yields *chunks*, not lines,
  so `stream_exec` buffers and splits on newlines.)
  - `modal.App.lookup(MODAL_APP_NAME, create_if_missing=True)`.
  - Test image: `modal.Image.debian_slim(python_version="3.12").add_local_dir(<harness>, "/harness")`.
  - Coding: `open_session` creates one sandbox (`timeout=45*60`, `idle_timeout=10*60`) and stores the id;
    `run_tests` execs `python /harness/run_tests.py` with the JSON on stdin (⚠️ VERIFY the stdin API:
    `p.stdin.write(...)`, `write_eof()`, `drain()`). Recreate the sandbox if it's gone.
  - Defense: **one shared project image**, built once at startup:
    `debian_slim(python_version="3.12").pip_install("fastapi", "uvicorn", "httpx", "aiosqlite", "flask")`
    (+ the union of the sample apps' `requirements.txt`). Uploads whose requirements aren't covered get a
    cached per-`content_hash` image layered on top. Per chaos run (baseline or verify): `Sandbox.create(...,
    timeout=60)` → write the project files (edited files for verify) under `/work/app/` and `attack.py` at
    `/work/attack.py` at runtime (⚠️ VERIFY V7: sandbox filesystem API vs exec + stdin) → start the
    entrypoint in the background from `/work/app/` → readiness probe (poll the port ≤ 10 s; `modal.Probe`
    if available) → exec `python /work/attack.py` and stream stdout lines → terminate. Writing files at
    runtime instead of baking them into an image means verify runs don't rebuild an image.
  - `stream_exec` yields raw lines; `chaos.py` parses each into `ChaosMetric` (bad lines → `system` note,
    skipped) and appends to the timeline + broadcasts.
  - Network: the attack only needs loopback. Restrict egress if the SDK supports it (⚠️ VERIFY
    `block_network` / `cidr_allowlist` in the Sandbox reference and that loopback still works).
- **LocalRunner (dev only):** the same harness via `asyncio.create_subprocess_exec` in a temp dir with
  timeouts. It also implements `start_project` / `stream_exec` / `stop_project` (the app's entrypoint as a
  subprocess with its requirements installed in an isolated environment, e.g. `uv run --no-project
  --with-requirements requirements.txt …`), so ST can validate sample apps and SS can build the chaos lab
  before Modal works. It refuses to start unless `RUNNER=local` and `ALLOW_LOCAL_RUNNER=1`. Never used in
  production.

---

## 13. Data

Owner: **ST**. Supports SG (problems, coding evals) and SS (sample apps, defense evals).

### 13.1 Problem bank
- **Format:** `data/problems/<slug>/` with `problem.json` (`ProblemSpec` minus the sibling-file fields),
  `statement.md`, `reference.py`, optional `brute.py` and `illustration.png`.
- **Originality:** every statement is written fresh with its own story and names. Never copy titles, text or
  examples from LeetCode/HackerRank/etc. Classic *patterns* are fine (they're not copyrightable); copied
  wording is not.
- **Coverage target (P0 12 → P1 30 → P2 40+):**

| Pattern | Easy | Medium | Hard |
|---|---|---|---|
| Arrays & hashing | 2 | 2 | – |
| Two pointers / sliding window | 1 | 3 | 1 |
| Stack / monotonic stack | 1 | 2 | – |
| Binary search | 1 | 2 | 1 |
| Linked list (as a list of values) / intervals | 1 | 2 | – |
| Trees / graphs (BFS/DFS, given as arrays/adjacency lists) | 1 | 3 | 1 |
| Heap / greedy | – | 2 | 1 |
| Dynamic programming | – | 2 | 2 |

  P0's 12 = 4 easy, 6 medium, 2 hard across different patterns. Mark 1 easy + 1 medium as **demo problems**
  (§20).
- **Rubric quality bar:** 3–6 steps with `order`; at least one step about edge cases; each step's 3 hints
  escalate and contain no code; `look_for` lists concrete code/speech signals; edge cases each map to ≥ 1
  hidden test (`edge_case_id`); 2 wrap-up questions.
- **Pipeline:**
  1. `python -m crucible.datatools.draft_problem --pattern "sliding window" --difficulty medium` → drafts
     `problem.json` + statement + reference + brute with Muse Spark 1.3 (or Spark Open on Baseten for bulk
     runs) into `data/problems/_drafts/`.
  2. `python -m crucible.datatools.validate_problems [slug|--all]` checks: the schema; the reference passes
     every test via LocalRunner; the brute-force solution agrees with the reference on 200 random inputs (when
     the draft includes an input generator); the starter compiles and fails at least one test; every edge
     case has a test; hints don't contain code (same leak-guard heuristic); the time limit is set.
  3. Human review checklist (ST): the statement is clear and original, the examples are correct, the
     rubric matches how a real interviewer would grade. Then move it from `_drafts/` to `data/problems/`.
- **P1:** Muse Image illustrations for grid/tree/graph problems: generated offline, reviewed by a human,
  committed as PNGs (`/v1/images/generations`, `muse-image-1.0`, $0.01/image).

### 13.2 Defense sample apps
Each in `data/defense_apps/<slug>/`: `app/` (FastAPI, 150–400 lines, written in a realistic "AI-generated"
style: plausible, readable, subtly wrong), `requirements.txt`, `crucible.json`, `flaws.json` (ground truth),
`fix.patch` (reference fix).

| Slug | Seeded flaw | Chaos invariant | P |
|---|---|---|---|
| `bank-transfer` | `/transfer` reads the sender balance, awaits an async "fraud check" (`await asyncio.sleep(0.03)`), then writes `balance - amount`; no transaction or lock (target headline: "Under 200 concurrent transfers, $1,240 disappeared") | total balance constant | P0 (demo) |
| `ticket-drop` | check-then-insert on seat availability (target: "Under 150 concurrent checkouts, 38 seats double-booked"); second finding: O(n²) unindexed seat-recommendation loop | each seat sold at most once; sold ≤ capacity | P0 |
| `report-service` | blocking `time.sleep`/CPU work inside an `async def` route | `/health` p95 < 200 ms while `/report` is loaded | P0 |
| `search-api` | O(n²) dedupe per request | p95 grows with dataset size (threshold) | P1 |
| `rate-limiter` | unsynchronized counter + unbounded dict | allowed ≤ limit per window | P1 |

`flaws.json`: `[{id, category, file, line_start, line_end, explanation, expected_fix, grill_expected_points,
chaos_invariant}]`. `reference_attack.json`: `{flaw_id, concurrency, duration_s, functions}`, or a list with one
per chaos flaw. `validate_apps` (`make validate`) checks: the app boots in the runner, every reference attack
**breaks** the original, and with the reference fix applied the same attack **holds**.

### 13.3 Evals (`data/evals/`)
- **Coding** (`evals/coding/*.jsonl`): scripted timelines (editor events + transcript + runs) with expected
  policy outcomes. Minimum set: `clean-solve` (few or no interventions), `skips-empty-input` (MISSED_STEP fires
  on the edge-case step), `off-by-one` (BUG_SUSPECTED), `paste-solution` (PASTE flag, no accusation),
  `silent-coder` (SILENT), `plan-mismatch` (PLAN_MISMATCH), `asks-for-answer` (ASKED, leak guard holds),
  `passive-mode` (nothing delivered except asks), `stuck-idle` (IDLE), `wrong-approach-brute-force`.
- **Defense** (`evals/defense/*.json`): per sample app, expected findings (for audit recall) and expected
  verdicts (baseline broke, verify with `fix.patch` held).
- **Built so far** (`backend/tests/evals/cases/`, run by `make evals`; the runner also reads `data/evals/coding/`):
  `skips-empty-input` and `off-by-one` on all three gold problems, plus `coded-before-plan`, `states-plan-early`
  (no false "what's your approach?" once the plan is older than 90 s), `plan-mismatch` and `spoken-question` (a
  question asked out loud without Ask is answered; a rhetorical one isn't). An eval passes in ≥ 2 of 3 runs.
  Expectation keys: `fires`, `never`, `limits` (at most N of a trigger), `max_shown`, `no_leak`, `flags`, `saw`
  (what the analyzer reported).

---

## 14. Frontend

Owner: **LG** (UI). Capture/replay libs: **SG**. Defense helpers: **SS**.

LG scaffolded `frontend/` and built the landing page (most of FE-1) on the `frontend` branch. His detailed plan
is in `frontend-schematic/CRUCIBLE_FRONTEND_PLAN.md`, and the UI rules are in `frontend-schematic/UI_TEMPLATE.md`.
Until S-1 and OPS-2 land, the frontend uses two **dev-only bridges**, and neither may appear in the demo:
- `src/types/contracts.draft.ts`, hand-transcribed from §7 and §8.2 behind an `@/types` barrel. It's deleted
  the day `contracts.ts` is generated.
- A `FixtureTransport` in `src/lib/dev-fixtures/`, enabled by `NEXT_PUBLIC_FIXTURES=1`. It plays the same
  JSONL format as the backend's MOCK mode (§14.6) and is removed once MOCK mode works.

### 14.1 Routes
| Route | Content |
|---|---|
| `/` | Hero, the two mode cards, "how it works", the Meta models strip |
| `/coding` | Setup form (difficulty, topic, feedback, voice, speak replies); pre-fills from the `?topic=&feedback=` the landing page's start dialog sends |
| `/coding/[id]` | `InterviewRoom` in coding configuration |
| `/defense` | Sample app cards (+ zip upload, P1) |
| `/defense/[id]` | Stage stepper: Audit → Chaos → Grill → Fix → Verify → Verdict |
| `/report/[id]` | Report + replay |

### 14.2 InterviewRoom (shared)
Layout (desktop ≥ 1280 px):
- **Top bar:** phase stepper, timer (remaining), feedback-mode badge, mic state, **End**.
- **Left (30%):** problem panel (markdown statement, examples, constraints, illustration) or, in defense, the
  finding card (title, explanation, chaos summary, file/lines).
- **Center (45%):** Monaco (Python, `quickSuggestions: false`, `wordBasedSuggestions: "off"`, minimap off),
  file tabs (defense), **Run** / **Submit** (coding) or **Verify** (defense). Bottom drawer: TestPanel (cases,
  stdout/stderr).
- **Right (25%):** InterviewerPanel: interviewer state indicator (idle / listening / thinking / speaking),
  message list (interventions + replies; level chip), live captions (partial transcript), **Ask** (hold to
  talk / chat box), **Hint**, mic toggle. **Interviewer's notes** toggle (NotesPanel): rubric steps with live
  statuses, suspected issues, stated plan. Off by default; useful for the demo and for judges.

### 14.3 Capture libs (SG)
- `lib/capture/editor.ts`: `attachEditorCapture(editor, send, {startedAtMs, file?})` →
  `{snapshot(), flush(), setFile(file), programmatic(edit), dispose()}`:
  - `editor.onDidChangeModelContent(e)` → `EditorEvent{kind: e.isUndoing ? "undo" : e.isRedoing ? "redo" :
    "change", changes: e.changes.map(c => ({range_offset: c.rangeOffset, range_length: c.rangeLength,
    text: c.text})), version: e.versionId, t}`.
  - Monaco fires `editor.onDidPaste(...)` *after* the paste's content change, so it relabels that buffered
    change as `paste` with `pasted_chars`. (If it ever fires first, it labels the next change.)
  - A flush (`setValue`) and anything inside `programmatic(edit)` (resetting to starter code, loading a file)
    become a snapshot, never typing, so they can't trigger paste or bulk-insert notes.
  - `document.visibilitychange` → `hidden` / `visible`; `window.blur` / `window.focus` → `blur` / `focus`.
  - Attaching sends one snapshot of the editor's current code (the starter code, or the code restored after
    a reload): the baseline that later edits apply to (§9.3) and that CODED_BEFORE_PLAN counts from (§9.5).
  - Batch every 500 ms; snapshot every 20 changes, every 15 s with changes, and before run/submit/verify
    (the room calls `snapshot()`).
  - `t` comes from `performance.now()`, aligned once to `session.started_at`, so system clock changes don't
    move it.
  - The editor parameter is a structural type, so any Monaco editor fits without importing Monaco here.
  - Tests: `node --experimental-strip-types --test "frontend/src/lib/**/*.test.mjs"` (Node's built-in runner;
    no new dependency).
- `lib/capture/audio/`: `getUserMedia({audio: {echoCancellation: true, noiseSuppression: true}})` →
  AudioWorklet → downsample to 24 kHz → Int16 → 1,920-sample (80 ms) frames → binary WS. Pause sending while
  TTS is speaking (avoids transcribing the interviewer).
- `lib/replay.ts`: `codeAt(timeline, file, t)` = the last snapshot ≤ t plus the edits after it (same algorithm
  as §9.3).

### 14.4 Defense views
- **Audit:** React Flow topology (auto-layout with dagre/elkjs; flagged nodes red) + findings list (severity
  chips; click → highlight node + open the file preview).
- **Chaos lab:** live Recharts line charts (rps, p95 ms) + counters (errors, invariant violations) streaming
  from `defense.chaos.metric`; a big verdict banner ("BROKE: $1,240 missing"); a collapsible generated attack
  script.
- **Grill:** a large question card, a 90 s countdown, live captions, Answer by voice or chat, then the
  points-hit/missed feedback. P1: a "Circle it" pen on the topology diagram (`defense.circle`); the node from
  `defense.sam.highlight` pulses.
- **Stage label:** from `lib/defense.ts` (SS), derived from phase + latest chaos/verify/verdict data (§11.2).
- **Fix:** InterviewRoom with the finding files.
- **Verify / Verdict:** charts overlaid before vs after; a "Merge gate" PASS/FAIL panel with reasons.

### 14.5 Report + replay
- Header: overall score, dimension bars with evidence tooltips, summary, 3 strengths, 3 improvements,
  metrics grid.
- **Replay:** a scrubber over the session duration with markers by kind (interventions, runs, flags, moments,
  chaos verdicts); a read-only Monaco showing `codeAt(t)`; a transcript pane auto-scrolling to `t`;
  play/pause at 1×/4×/16×. Clicking a moment card seeks to it.
- Defense extras: findings, before/after charts, grill turns, verdict.

### 14.6 Mock mode
With `MOCK=1` the backend replays `mock/fixtures/<scenario>.jsonl` (recorded `ServerMessage`s with relative
timestamps) on the session socket and serves canned REST responses. Each line is
`{"dt_ms": <ms since the previous line>, "msg": <ServerMessage>}`; client messages are accepted and logged, not
answered. In MOCK mode a session's id is its scenario name (`/coding/coding-active`). Scenarios: `coding-active`,
`coding-passive`, `defense-bank-transfer`, `report-coding`, `report-defense`. SG and SS keep their fixtures
in sync with contract changes (CI validates fixtures against the contracts). Fixtures live in
`backend/crucible/mock/fixtures/`; defense ones are **recorded** from a real local session
(`python -m crucible.mock.record defense-bank-transfer --apps-dir ... --project ...`, no API key needed), and
`MOCK_SPEED` speeds up the replay.

MOCK is only ever switched on explicitly: a timeout, a missing credential or a Modal failure in a real
session never falls back to recorded data (it follows §21: a real fallback model, or an `error` verdict with
a retry button), because recorded results shown as live would be a faked demo.

### 14.7 TTS (`lib/tts.ts`)
`speechSynthesis` with a chosen English voice (prefer a natural voice when available), a queue, `cancel()`
when the candidate starts speaking (barge-in), and an `onstart`/`onend` that drives the speaking indicator.
No third-party TTS (e.g. ElevenLabs): it would be the only non-Meta model call at runtime, needs another
key, and `speechSynthesis` has no outage to fall back from.
- **API:** `createTts({onStart, onEnd, onBlocked, onVoices, voiceName})` → `{speak(text), cancel(),
  setMuted(bool), setVoice(name | null), warm(), unlock(), dispose(), speaking, blocked, voices, voice,
  supported}`, plus `rankVoices`, `isNaturalVoice`, `voiceLabel` and `loadVoiceChoice`/`saveVoiceChoice`
  (localStorage, per browser). Without `speechSynthesis` (or on the server render) every call is a no-op.
- **Voice, as human as the browser allows:** waits for `voiceschanged` (at most 1.5 s), then ranks the English
  voices, en-US first within each tier: Edge's neural voices ("… Online (Natural)", Ava, Andrew, Emma and Brian
  first), macOS "(Premium)" then "(Enhanced)" voices, any other natural or neural voice, Google's ("Google US
  English", then "Google UK English Female"), then Samantha, Daniel, Karen and Moira, then the rest. The novelty
  voices (Albert, Bad News, Bells, Zarvox, …) and the robotic Eloquence ones (Eddy, Flo, Grandma, Grandpa, Reed,
  Rocko, Sandy, Shelley) are never picked or listed. The candidate's own pick wins when it's installed.
- **Prosody:** rate 1.05, pitch 1. One utterance per sentence, so the first sentence starts at once and nothing
  breaks mid-phrase; only a sentence over 220 characters (Chrome cuts an utterance off after about 15 s) splits,
  at its commas, semicolons and colons. Markdown is read as plain text and code blocks are skipped. `warm()`
  speaks one silent, empty utterance in the default local voice to start the engine (the room calls it on load
  and on the first click; Google's network voices don't warm up, each sentence is its own request).
- **Queue:** sentences are spoken one at a time. `onStart` fires when the first one starts and `onEnd` once the
  queue is empty or cancelled. Chrome can wedge its queue when `speak()` follows `cancel()` at once (seen with
  the room's remount in development), so the next sentence waits 120 ms after any cancel, and a sentence the
  busy engine hasn't started within 3 s is cleared and retried once, then skipped. A lost end event is caught
  once the engine goes idle, and a sentence stuck far past its length is cut, so the mic is never held silent
  for good.
- **Blocked:** a browser that refuses to speak before the user has interacted with the page (`not-allowed`, or
  Safari dropping it silently) sets `blocked` and holds the newest message; the room shows "Turn on voice",
  whose click calls `unlock()`.
- **The room:** speaks each new interviewer message with `speak: true` as it appears, and calls the audio
  capture's `setPaused(true)` from `onStart` until `onEnd`, so the mic sends silence (§8.3). Holding Ask cancels
  the speech. The header has the mute toggle and a voice picker (the ranked list, remembered per browser). When
  the best voice installed is Google's or older, a one-line hint suggests Microsoft Edge or a macOS Premium voice
  (System Settings → Accessibility → Spoken Content).

---

## 15. Meta model integration

### 15.1 Client wrapper (`models/llm.py`, SG)

```python
client = OpenAI(base_url=settings.META_BASE_URL, api_key=settings.MODEL_API_KEY)  # also AsyncOpenAI

async def complete_json(role: ModelRole, messages: list[dict], schema: type[T], *,
                        effort: str | None = None, timeout_s: float = 12, images: list[str] = ()) -> T:
    """Structured output via client.beta.chat.completions.parse(model=..., response_format=schema,
    reasoning_effort=effort). Retries once on 429/5xx with jittered backoff, then walks the role's fallback
    chain. Logs model, latency, tokens and estimated cost to the timeline (system) and stdout."""

async def complete_text(role: ModelRole, messages, *, effort=None, timeout_s=8) -> str: ...
```

- **Roles → defaults** (`models/registry.py`, overridable by env):

| Role | Default | Effort | Fallback chain |
|---|---|---|---|
| `analyzer` | `muse-spark-1.3` | minimal | skip tick |
| `interviewer` | `muse-spark-1.3` | low | canned/rubric text |
| `classifier` (P1) | `muse-spark-1.3` | minimal | treat as thinking aloud |
| `complexity` (P1, COD-5) | `muse-spark-1.3` | low | leave the answer ungraded (null) |
| `conversation` (warm-up, replies, probes, check-ins) | `muse-spark-1.3` | minimal (short lines; every second is a pause the candidate hears) | the canned line |
| `grill_eval` | `muse-spark-1.3` | low | Spark (minimal) → Spark Open (Baseten) |
| `grill_check` (DEF-13) | `muse-wonder-1.0` | low | Spark Open; runs in parallel with `grill_eval`, and only points both mark count (§11.5) |
| `audit` | `muse-wonder-1.0` | xhigh | `muse-spark-1.3` (high) → `flaws.json` (samples only) |
| `report` | `muse-wonder-1.0` | high | `muse-spark-1.3` → metrics-only template |
| `attacker` | `muse-spark-1.3` | low | Spark (medium) → reference attack (sample apps only) |
| `drafter` (datatools) | `muse-wonder-1.0` | high | Spark (medium) → Spark Open |
| `vision` (P2) | `muse-spark-1.3` with image input | low | skip |
| `assistant` (P1, §11.9) | `muse-spark-1.3` | low | "assistant unavailable" message |

Attacker and grill effort were re-measured on 2026-10-28 with the real prompts (bank-transfer-min, 4 calls each):
the attacker took p50 26 s / max 30 s at high (timing out against its 30 s budget), 18.5 s at medium and 6.6 s at
low, with every attack valid; at low, 2 of 2 full Defense runs broke the app. grill_eval took 4.2 s at medium and
3.0 s at low, marking the same points.

- `reasoning_effort` values: `minimal | low | medium | high | xhigh | max` (`none` returns 400 on Spark and
  Wonder). Live roles (analyzer, interviewer, classifier, grill_eval) use the lowest effort that works.
  One-shot roles use the strongest setting that fits their timeout. Measured 2026-10-27 on `bank-transfer-min`:
  audit Wonder high 31 s / $0.10 (2 topology nodes) vs xhigh 44 s / $0.15 (6 nodes); attacker Spark medium 14 s,
  Spark high 18 s, Wonder medium 20 s, Wonder high 29 s (30 s budget), all valid; grill_eval Spark medium 4–5 s,
  Spark high 7–8 s (10 s budget), Wonder low 4–11 s, all marked the same points.
- **Dev cost switch:** `USE_CONTRIBUTOR_MODELS=1` maps `muse-spark-1.3` → `muse-spark-1.3-contributor`
  ($0.10/$0.20 per 1M tokens, but content may be used for training and the limit is 150 RPM). Use it only
  with synthetic data, never for real users' sessions. It doesn't support `max` effort.
- **Muse Spark audio:** we don't send audio to Spark (1.3's audio isn't fully reliable per the docs); all
  speech goes through Muse Voice Transcribe.
- **Partner endpoints** (OpenAI-compatible, same wrapper with a different `base_url`):
  - Spark Open: Baseten, `SPARK_OPEN_MODEL=meta-models/muse-spark-open-1026` (the hackathon guide says to
    use this id, not `muse-spark-open`). ⚠️ VERIFY the base URL in Baseten's docs.

### 15.2 Verified API facts (from dev.meta.ai docs, Oct 26 2026)
- Base URL `https://api.meta.ai/v1`; Bearer auth; key in env `MODEL_API_KEY` (pass explicitly to the SDK).
- Protocols: Responses (`/v1/responses`), Chat Completions, Messages (Anthropic-style).
- Structured output: Chat Completions `response_format={"type":"json_schema","json_schema":{...}}` or
  `beta.chat.completions.parse(response_format=PydanticModel)`; Responses uses `text.format`. Limits:
  no recursive schemas, nesting ≤ 10, ≤ 5,000 properties.
- Reasoning: Chat Completions `reasoning_effort`; Responses `reasoning.effort`.
- Context: Spark 1.3 and Wonder 1.0 both have 1,048,576 tokens.
- ASR: realtime `wss://api.meta.ai/v1/asr/realtime` (handshake auth, PCM_24KHZ/PCM_16KHZ, modes
  PUSH_TO_TALK / ENDPOINTING / DIARIZATION, ≤ 60 min per session, no word timestamps); file
  `POST /v1/asr/transcribe` (WAV mono 16-bit 16/24 kHz, ≤ 10 min, ≤ 32 MB).
- Images: `/v1/images/generations`, `/v1/images/edits` (`muse-image-1.0`).
- SAM 3.1: `POST /v1/responses`, `model: "sam-3.1"`, a short noun phrase + image; returns box/mask records.
- No text-to-speech model is offered.

### 15.3 Cost (list prices; ⚠️ re-check before the demo)
| Item | Price | Per session estimate |
|---|---|---|
| Spark 1.3 | $1.25 in / $4.25 out per 1M ($0.15 cached in) | coding: ~80 analyzer calls ≈ $0.25 |
| Wonder 1.0 | $4 in / $20 out per 1M | report ≈ $0.15–0.25; audit ≈ $0.20–0.40 (cached per project) |
| Voice Transcribe | $0.18 per audio hour | ≈ $0.09 per 30 min |
| Muse Image | $0.01 per image | offline only |
| SAM 3.1 | $2.50 per 1k images | P2, negligible |
| Modal | compute per second | pennies per session |

≈ **$0.50–1.00 per session**. Each teammate has $150 of Meta credit; set a **spend-limit notification** on
the Billing page. `MAX_SESSIONS_PER_IP_PER_DAY=10` on the deployed app.

---

## 16. Work packages

Format: **ID — title** (owner · priority · depends on) followed by "done when".

### Day 0 (Mon Oct 26 evening): everyone
- **S-0 — Scaffold** (SS · P0 · –): the layout from §6; FastAPI `/api/health`; `Makefile` targets
  (`install`, `dev`, `check`, `contracts`, `validate`, `evals`); `.env.example` (§19.2); ruff/eslint/prettier;
  CI running `make check`. The Next.js part is already done: LG scaffolded `frontend/` (Next 16, Tailwind v4,
  shadcn) on the `frontend` branch, so merge that first and wire it into `make dev` and CI
  (`pnpm --dir frontend …`).
  *Done when* `make dev` serves both apps and CI is green on `main`.
- **S-1 — Contracts v1** (SG + SS · P0 · S-0): every model in §7 + `export.py` + the generated TS; fixture
  JSON for each top-level model under `backend/tests/fixtures/` validated in tests.
  *Done when* `make contracts` is clean and LG and ST have reviewed the PR.
- **S-2 — Accounts and credits** (everyone · P0): claim the Meta credits (form; each person individually, by
  Nov 4 9 PM ET), add a card, set a spend-limit notification; request Modal, Baseten and Fireworks credits;
  share keys through a password manager, never in git or Discord.

### Srinithin: shared engine + coding mode
- **ENG-1 — Hub, sessions, timeline, store glue** (P0 · S-1): `POST/GET /api/sessions`, WS endpoint, hello →
  `session.state`, `Timeline.append/read` with payload validation, phase machine helpers.
  *Done when* a test client connects, sends events and reads them back from `/timeline` in order.
- **ENG-2 — CodeState + replay parity** (P0 · ENG-1): §9.3, plus `lib/capture/editor.ts` and `lib/replay.ts`.
  *Done when* the parity fixture reconstructs identically in Python and TS, and paste/bulk counts are correct.
- **ENG-3 — Model wrapper** (P0 · S-1): §15.1 roles, fallbacks, cost logging, `python -m
  crucible.models.smoke` (one parse call per role).
  *Done when* the smoke script passes against the live API.
- **ENG-4 — Analyzer** (P0 · ENG-2, ENG-3, DATA-1): scheduler + prompt + `Analysis` + `notes.update`.
  *Done when* on the 3 gold problems, `skips-empty-input` and `off-by-one` produce the expected step/issue in
  ≥ 2 of 3 runs.
- **ENG-5 — Policy + hint ladder + passive mode** (P0 · ENG-4): §9.5 with unit tests per rule.
  *Done when* every rule has fires/doesn't-fire tests and the coding evals' policy expectations pass with
  recorded analyses.
- **ENG-6 — Interviewer + leak guard** (P0 · ENG-5): §9.6, canned lines, intro pre-generation.
  *Done when* `asks-for-answer` never leaks (20 attempts) and the intro plays within 1 s of joining.
- **ENG-7 — VoiceBridge + audio capture** (P1, but start Day 3 · ENG-1): §9.7 + `lib/capture/audio`.
  *Done when* speaking in the room produces final turns in the timeline within ~1.5 s of finishing, and the
  fallback works with realtime disabled.
- **ENG-8 — ReportBuilder** (P0 · ENG-5): §9.8.
  *Done when* both mock-free sessions (coding and defense) produce a valid `Report` within 90 s, and the
  fallback works with Wonder disabled.
- **COD-1 — ProblemBank + problem API** (P0 · S-1, DATA-1).
- **COD-2 — Coding phases, timers, wrap-up** (P0 · ENG-1, ENG-6).
- **COD-3 — Test service** (P0 · RUN-1): run/submit → `run.result`, hidden-input redaction.
- **COD-4 — Integrity detectors** (P0 · ENG-2).
- **COD-5 — Coding report extras** (P1 · ENG-8). **Built Oct 28** (§10.5).
- **COD-6 — Voice question classifier; plan-mismatch and coded-before-plan rules** (P1 · ENG-7).
- **VIS-1 — SAM sketch + proctor** (P2 · COD-2).

### Shreyas: defense mode + runner + infra
- **RUN-1 — Runner protocol, harness, LocalRunner** (P0 · S-1): §12.
  *Done when* the harness passes comparator unit tests and a timeout test, and LocalRunner runs the 3 gold
  problems.
- **RUN-2 — ModalRunner for tests** (P0 · RUN-1): a warm sandbox per coding session.
  *Done when* a Run on a warm sandbox returns in < 2 s (measure and record it) and the sandbox is cleaned up
  on end.
- **RUN-3 — ModalRunner for projects** (P0 · RUN-2): shared project image, runtime file writes, readiness,
  streaming exec (§12). Until DATA-4 lands, test against a minimal racy app in `backend/tests/fixtures/`.
- **DEF-1 — Project store + samples API** (P0 · S-1, DATA-4); zip upload (P1).
- **DEF-2 — Audit** (P0 · ENG-3): §11.3 + `defense.audit` + cache.
  *Done when* the audit finds every seeded flaw in the 3 P0 sample apps (≥ 2 of 3 runs).
- **DEF-3 — AttackWriter + template + validator** (P0 · DEF-2).
  *Done when* the validator rejects the bad-script test corpus and the writer produces valid scripts for all
  P0 findings.
- **DEF-4 — Chaos execution + metrics + verdict** (P0 · RUN-3, DEF-3).
  *Done when* every P0 sample breaks at baseline and holds with `fix.patch` applied, with live metrics in the
  UI.
- **DEF-5 — Grill** (P0 text, P1 voice · ENG-6, ENG-7): §11.5, with code-computed scoring.
  *Done when* scoring unit tests cover root cause missing / hit / SAM bonus, and `defense.audit` never
  carries an explanation (test).
- **DEF-6 — Fix stage + verify + verdict** (P0 · ENG-5, DEF-4).
- **DEF-7 — Defense report extras** (P1 · ENG-8).
- **DEF-8 — Attack refine loop** (P1 · DEF-4).
- **DEF-9 — "Circle the flaw" with SAM 3.1** (P1 · DEF-5, FE-6; **after IC3, and only with LG's OK**, since
  it needs a pen, a canvas PNG export and node boxes in FE-6): §11.7.
  *Done when* a circle drawn around the flawed node on a canvas PNG selects that node in ≥ 4 of 5 tries.
- **DEF-10 — Merge-gate card** (P2 · DEF-6; only after both P0 paths pass the demo script twice): §11.8.
- **DEF-11 — Muse fix assistant** (P1 · DEF-6, after IC2; needs the contract additions below with SG + SS
  approval, an `assistant` role in `models/registry.py` (SG), `chars_ai` in CodeState (SG) and a side panel in
  the fix stage (LG)): §11.9. Contracts: `AssistantEdit {file, new_code}`, `AssistantReply` (LLM output:
  `answer`, `edits`), `AssistantTurn`, `TimelineKind.ASSISTANT` and `ASSISTANT_APPLY`, the three messages in §8.2,
  `DefenseExtra.ai_assist`.
  *Done when* a candidate can ask, see a diff, accept it, verify, and the report shows the AI share.
- **OPS-1 — Deploy** (P0 · S-0): §19. *Done when* the deployed frontend runs a full coding session against
  the deployed backend.
- **OPS-2 — Mock replay engine + fixtures** (P0 · S-1): §14.6.

### Likhil: frontend
- **FE-1 — Shell, landing, design system** (P0 · S-0). The landing page and design tokens are done on the
  `frontend` branch; what's left is the app shell for the room and report pages.
- **FE-2 — API/WS clients + session store** (P0 · S-1): typed from `contracts.ts`, reconnect with backoff,
  `hello` on (re)connect.
- **FE-3 — InterviewRoom + Monaco + TestPanel** (P0 · FE-2, ENG-2 capture lib).
- **FE-4 — InterviewerPanel + NotesPanel + TTS + Ask/Hint** (P0 text, P1 voice · FE-3).
- **FE-5 — Coding setup + problem panel** (P0 · FE-2).
- **FE-6 — Defense flow** (P0 · FE-3, OPS-2 fixtures): picker, audit (React Flow), chaos charts, grill, fix,
  verdict.
- **FE-7 — Report + replay** (P0 · FE-2, ENG-2 replay lib).
- **FE-8 — Polish:** loading/error/empty states, mic/camera permission UX, keyboard shortcuts (Ctrl+Enter =
  Run), consistent motion (P1).

### Sharvil: data for both modes
- **DATA-1 — Problem template + 3 gold problems** (P0 · S-1; **by Tue Oct 27 night**): 1 easy, 1 medium,
  1 hard, written by hand to the quality bar. These unblock SG.
- **DATA-2 — Draft + validate tools** (P0 · RUN-1).
- **DATA-3 — Problem bank** (P0: 12 by Thu Oct 29; P1: 30 by Sun Nov 1; P2: 40+).
- **DATA-4 — Defense sample apps** (P0: 3 by Thu Oct 29 with `flaws.json` + `fix.patch` + reference chaos
  script; P1: +2).
- **DATA-5 — Evals** (P0: coding 6 + defense 3 by Sat Oct 31; P1: full list in §13.3).
- **DATA-6 — Muse Image illustrations** (P1).
- **DATA-7 — Demo data + rehearsal** (P0 · Mon Nov 2): the demo problem, the demo app, the demo script's
  expected behavior, and two dry runs.

---

## 17. Schedule

All times ET. Integration checkpoints (**IC**) are at 9 PM: everyone merges to `main`, and we run the
checkpoint script on a clean checkout.

| Day | Date | SG (engine + coding) | SS (defense + runner) | LG (frontend) | ST (data) |
|---|---|---|---|---|---|
| 0 | Mon Oct 26 | S-1 contracts with SS | S-0 scaffold, S-1 | FE-1 shell, Figma-level sketch of the room | Problem template, start the gold problems |
| 1 | Tue Oct 27 | ENG-1, ENG-3 | RUN-1, OPS-2 skeleton | FE-2, FE-3 (Monaco + capture) | **DATA-1 done**, start DATA-4 (`bank-transfer`) |
| 2 | Wed Oct 28 | ENG-2, ENG-4, COD-1 | DEF-1, DEF-2 | FE-3, FE-4 (text), FE-5 | DATA-2, `ticket-drop` |
| | **IC1** | | | | |
| 3 | Thu Oct 29 | ENG-5, COD-3, start ENG-7 | RUN-2, RUN-3, DEF-3 | FE-6 audit + chaos views (fixtures) | **12 problems**, **3 apps** |
| 4 | Fri Oct 30 | ENG-6, COD-2, COD-4, ENG-7 | DEF-4, DEF-5 (text) | FE-4 voice + TTS, FE-6 grill/fix | Evals v1, 20 problems |
| | **IC2** | | | | |
| 5 | Sat Oct 31 | ENG-8 | DEF-6, OPS-1 deploy | FE-7 report + replay | Evals, 25 problems |
| 6 | Sun Nov 1 | P1: COD-5, COD-6 | DEF-7, DEF-8, DEF-11 backend (after IC2) | FE-8, integration fixes; DEF-11 side panel if time allows | **30 problems**, apps 4–5 |
| | **IC3 + cut-line review** | | | | |
| 7 | Mon Nov 2 | Eval tuning, latency, P2 if green | Reliability; DEF-9 (P1) if IC3 is green and LG agrees; P2 (DEF-10) if green | Polish, demo-path UX; the DEF-9 pen only if agreed | DATA-7 demo data + rehearsal |
| 8 | Tue Nov 3 | **Feature freeze 12 PM.** Bug fixes only; record demo takes | same | same | Final data checks |
| 9 | Wed Nov 4 | Final video edit; **submit by 6 PM** (3 h buffer before the 9 PM deadline) | same | same | same |

Live sessions worth attending: Agents 101 (Tue 12 PM), **Agents 102: Verifiable Agents** (Wed 12 PM;
directly relevant to the policy and chaos verify), Fireworks + Muse open models (Fri 12 PM). Office hours: weekdays 10–11 AM in #office-hours.

**Checkpoint scripts**
- **IC1:** coding room on LocalRunner: type → analyzer → a nudge appears; Run returns results. Defense: the
  audit of `bank-transfer` renders in the UI.
- **IC2:** Modal runner for both modes; `bank-transfer` breaks live with streaming charts; grill Q&A (text);
  voice transcripts appear in the room.
- **IC3:** both modes end-to-end on the **deployed** build, including report + replay.

**Cut lines**
- At IC3, any mode that isn't end-to-end drops to its P0 path only, and all hands help it.
- If a mode still fails the demo script at Mon Nov 2 9 PM, the other mode becomes the video's hero, and the
  failing mode is shown only for the stages that work (never faked).
- P2 work starts only after both P0 paths pass the demo script twice in a row on the deployed build.

---

## 18. Testing and evals

- **Unit (pytest):** CodeState (offset application, undo/redo, paste counting), policy rules (every rule
  fires/doesn't fire), leak guard, harness comparators and timeouts, ScriptValidator corpus, metrics and
  moment selection, contract fixtures.
- **Integration (pytest, `-m integration`):** WS session with LocalRunner and a fake LLM (recorded
  responses), from the first event to the report.
- **Evals (`make evals`, costs credits, run manually):** the coding evals through the real analyzer + policy
  (pass if expectations hold in ≥ 2 of 3 runs); defense audit recall; chaos break/hold. Results are written to
  `backend/tests/evals/results/<date>.md`.
- **Frontend:** `tsc --noEmit`, eslint; P1 Playwright happy path against `MOCK=1`.
- **Latency budget** (targets; measured 2026-10-28 on the local build against the live Meta API, client clock;
  re-measure on the deployed build with `uv run python -m tests.evals.latency --url <backend>`):

  | Path | Target | Measured | How |
  |---|---|---|---|
  | Typing pause → nudge on screen | ≤ 6 s | p50 4.95 s, max 5.14 s (n=8) | 2.5 s pause, then the analyzer (Spark minimal: p50 2.3 s, p95 3.9 s over 31 calls), then delivery on the next 0.5 s tick |
  | Paste note (no model) | – | 2.6–3.0 s after the pause | the quiet window only |
  | Question → answer | – | p50 1.6–2.2 s, max 2.5 s (≤ 4.7 s in the ENG-6 check) | one Spark call |
  | Run → results | ≤ 3 s (warm sandbox) | 0.02–0.04 s on the local runner | Modal (RUN-2) not measured yet |
  | End of speech → final transcript | ≤ 2 s | 0.1–0.2 s | realtime Muse Voice (ENG-7 check, and in a real browser) |
  | Report | ≤ 90 s | 13–21 s on Wonder; Wonder twice ran past 90 s, so it now gets 45 s before Spark (worst case about 90 s) | |
  | Intro on join | ≤ 1 s | 1 ms | canned line |

  Nudges are held on purpose, which isn't latency: 45 s between unsolicited messages (counted from the last
  message, including answers), 2 analyses in a row for most rules, 20 s for a bug's line to settle, and 30 s of
  idle after a single failed run.

---

## 19. Deployment

### 19.1 Targets
- **Frontend:** Vercel (`frontend/`), env `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`.
- **Backend:** Railway or Fly.io from `backend/Dockerfile`; one instance (sessions live in memory); a volume
  mounted at `/data` for SQLite; WebSockets enabled; `CORS_ORIGINS` = the Vercel URL.
- **Modal:** `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` in the backend env; app name `crucible-runner`.

### 19.2 Environment variables (`.env.example`)
```
# Meta Model API
MODEL_API_KEY=
META_BASE_URL=https://api.meta.ai/v1
MODEL_ANALYZER=muse-spark-1.3
MODEL_INTERVIEWER=muse-spark-1.3
MODEL_GRILL=muse-spark-1.3
MODEL_AUDIT=muse-wonder-1.0
MODEL_REPORT=muse-wonder-1.0
MODEL_IMAGE=muse-image-1.0
MODEL_SAM=sam-3.1
ASR_URL=wss://api.meta.ai/v1/asr/realtime
ASR_MODEL=muse-voice-transcribe-1.0
USE_CONTRIBUTOR_MODELS=0          # dev only, synthetic data only
# Partners
BASETEN_BASE_URL=
BASETEN_API_KEY=
SPARK_OPEN_MODEL=meta-models/muse-spark-open-1026
MODAL_TOKEN_ID=
MODAL_TOKEN_SECRET=
MODAL_APP_NAME=crucible-runner
# App
RUNNER=modal                      # modal | local
ALLOW_LOCAL_RUNNER=0
DATABASE_URL=sqlite:///./var/crucible.db
MOCK=0
CORS_ORIGINS=http://localhost:3000
MAX_SESSIONS_PER_IP_PER_DAY=10
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
NEXT_PUBLIC_FIXTURES=0            # dev only: frontend FixtureTransport until MOCK mode works (§14)
```

---

## 20. Demo video and submission

### 20.1 The 3-minute video (draft script)
**Superseded by [docs/STORY.md](docs/STORY.md)** (v2: the story line first, Defense first, the Under the hood strip in every shot). Kept here for history.

| Time | Shot |
|---|---|
| 0:00–0:15 | Hook: "AI writes code in seconds. Interviews and production still ask: do you understand it?" Title: Crucible, two modes, one interviewer |
| 0:15–1:25 | **Live Coding Interview** (demo problem, active, voice on). Candidate states an approach out loud → starts coding → skips the empty-input case → the interviewer nudges (spoken) → the notes panel shows the step turning red, then green after the fix → a paste gets a neutral note → Run passes → Submit passes hidden tests |
| 1:25–2:30 | **Project Defense** (`bank-transfer`). Wonder audit → the topology node turns red → the chaos lab streams 200 concurrent transfers → "BROKE: $1,240 missing" → the grill question by voice → candidate explains → follow-up → candidate fixes it in the editor (the interviewer nudges once) → verify: the line holds flat → "Merge gate: PASS" |
| 2:30–2:50 | Report: scrub the replay (code writing itself, synced with transcript and nudges), moment cards |
| 2:50–3:00 | Meta models strip + "built during the hackathon" + repo URL |

Record each segment separately on the deployed build, at real speed (speed-ups allowed only if labeled).

### 20.2 Submission checklist (Wed Nov 4, by 6 PM ET)
- [ ] The repo is **public**; the README has the "Built during the hackathon" section and the model table.
- [ ] Video ≤ 3 min, link viewable without sign-in (test in a private window).
- [ ] Deployed URL works from a clean browser; spend limits set.
- [ ] All four members listed on the submission; one Representative submits.
- [ ] Every teammate has claimed their Meta credits (deadline Nov 4, 9 PM ET).
- [ ] No secrets in git history (`git log -p | grep -i key` sanity check); `.env` is in `.gitignore`.
- [ ] Every problem in `data/problems` has passed the originality review.

---

## 21. Risks and fallbacks

| Risk | Mitigation / fallback |
|---|---|
| Two modes dilute the build | Shared engine first; cut lines in §17; one hero mode in the video if needed |
| Frontend bottleneck (one UI owner) | Backend owners write the capture/replay/selector libs; MOCK fixtures from Day 1; shadcn components |
| Interventions feel noisy or wrong | Conservative thresholds, 2-analysis persistence, cooldowns, evals; passive mode as a safe default for skeptics |
| Analyzer latency | `reasoning_effort="minimal"` (measured 4 s vs 8–12 s at `low`, §9.4), static-first prompts, single-flight, skip on timeout |
| Solution leakage | Leak guard + rubric-text fallback + the `asks-for-answer` eval |
| Realtime ASR problems | Chunked file transcription → chat-only fallback; voice is P1, so text works end to end |
| Wonder slow or down | Spark fallback for audit and report; audit cached per project |
| Modal sandbox slow to start | Warm sandbox per coding session; pre-build sample-app images at startup; LocalRunner for dev |
| Chaos doesn't break a sample | Sample apps are validated with a reference script (`validate_apps`); the demo uses `bank-transfer` |
| Credits run out | Contributor models in dev with synthetic data, spend notifications, session limits, cached audits |
| Problem text rights | Original statements only + review checklist (§13.1) |
| Demo-day failure | Pre-recorded takes on the deployed build by Tue Nov 3; never present MOCK as live |

**Timeouts:** analyzer 12 s · interviewer 6 s · conversation 6 s · classifier 3 s · complexity 8 s (20 s guard, report time) · grill eval 20 s (Spark medium measured 4–15 s) · audit 120 s · report 45 s per model (Wonder measured 15–21 s, once over 90 s; then Spark) ·
attack writer 30 s · test run 10 s · chaos run 60 s · ASR handshake 10 s · SAM 5 s · image 20 s.

---

## 22. Rules for coding agents

These apply to Muse Code, Claude Code and humans alike.

1. **Stay in your work package.** Touch only the directories its owner owns (§6) plus tests. If you need a
   change elsewhere, note it in the PR description instead of making it.
2. **Contracts are frozen.** Don't edit `backend/crucible/contracts/` unless the work package says so; any
   change needs SG + SS approval, `make contracts`, and updated fixtures in the same PR. Never edit
   `frontend/src/types/contracts.ts` by hand.
3. **Every model call goes through `models/llm.py`** (or `asr.py` / `sam.py` / `image.py`). No direct SDK calls
   elsewhere. No model ids hard-coded outside `registry.py`.
4. **Prompts live in `prompts/*.md`**, loaded at startup. No inline prompt strings longer than one line.
5. **LLM suggests, code decides.** A model's output never directly triggers a user-visible message, an
   execution or a phase change without passing through code that validates it.
6. **Structured-output models:** no defaults, all fields required, `X | None` for optional, no recursion.
7. **No untrusted code outside the Runner.** Candidate code, project code and attack scripts run only via
   `Runner`. `LocalRunner` is dev-only.
8. **Secrets:** read via `config.py` only; never log them; never send them to the browser.
9. **Tests with every PR:** unit tests for logic; update fixtures for message changes. `make check` must pass.
10. **⚠️ VERIFY items:** before coding against one, read the linked doc, then update §23 with what you found.
11. **Small PRs** (< 400 changed lines when possible), branch `feat/<area>-<thing>` or `fix/<area>-<thing>`,
    Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`), 1 review from the area owner.
12. **Don't add dependencies** without listing them and the reason in the PR description.
13. **Never copy problem text from the internet**, and never commit generated problems that haven't passed
    `validate_problems` + human review.
14. When this plan is wrong or incomplete, fix the plan in the same PR.
15. **Keep your role plan in `plan/` current.** When a date, an interface or the scope in it changes, update
    it (and this file, if the spec changed) in the same PR.

---

## 23. Things to verify

| # | Item | Where to check | Owner | Status |
|---|---|---|---|---|
| V1 | Full `RealtimeHandshakeRequest` schema; ENDPOINTING event fields (`turnId`, final text, `startMs`/`endMs`) | dev.meta.ai/docs/api-reference/voice/realtime, /docs/speech-to-text | SG | done (2026-10-27, docs + live): handshake fields `authorization.accessToken`, `audioEncoding` (`PCM_24KHZ`/`PCM_16KHZ`, required), `model`, `mode` (`PUSH_TO_TALK` default, `ENDPOINTING`, `DIARIZATION`), `partialMode` (`CUMULATIVE` default), `emitAudioProgress` (default true), `keywords`, `languageBias`. The final text is in `speechComplete{turnId, transcript}`; partials carry no `turnId`; realtime has only `audioProcessedMs` (no `startMs`/`endMs`), the file endpoint's `turns` have `startMs`/`endMs`. Limits: 60 min per stream, at most 5 s of audio ahead of processing. Live: stream open in 0.4–0.6 s, final turns 0.1–0.2 s after speech ends, the file endpoint 2.3 s for 13 s of audio. Realtime may merge two sentences into one turn or split one; the file endpoint sometimes repeats a word or adds a zero-length duplicate turn (dropped) |
| V2 | How prompt caching triggers (automatic prefix caching?) | dev.meta.ai/docs (pricing mentions cached input) | SG | open |
| V3 | `reasoning_effort` with `beta.chat.completions.parse` on Spark 1.3 and Wonder 1.0 | /docs/reasoning, /docs/structured-output | SG | done: works on `muse-spark-1.3` (minimal, low, medium) and `muse-wonder-1.0` (high). Smoke run 2026-10-27, 9 of 9 roles passed. Also works: Spark high, Wonder medium and xhigh (benchmark 2026-10-27, §15.1) |
| V4 | Structured output support on `muse-wonder-1.0` | /docs/models, /docs/structured-output | SG | done: `muse-wonder-1.0` returns valid structured output through `parse` at effort high (about 2 s for a tiny schema) |
| V5 | ~~Glimmer model id + host~~ (Glimmer dropped 2026-10-27; the attacker uses Spark) | — | SS | dropped |
| V6 | Baseten base URL for `meta-models/muse-spark-open-1026` | docs.baseten.co | ST | open |
| V7 | Modal: Sandbox stdin API, writing files into a running sandbox, readiness probes, egress restriction + loopback | modal.com/docs/sdk/py/latest/Sandbox | SS | done (2026-10-27): stdin writes, exec, a port probe and streaming work (stdout arrives in chunks); `block_network=True` blocks egress (checked) and loopback still works |
| V8 | Muse Code headless/non-interactive mode (for the optional refactor handoff) | dev.meta.ai/lp/muse-code, `muse --help` | SS | open |
| V9 | SAM 3.1 box/mask record parsing details (also needed for DEF-9) | dev.meta.ai/docs/sam/segmenting | SG | open |
| V10 | Muse Image request/response format for illustrations (also DEF-10's card) | dev.meta.ai/docs/image-generation | ST | open |
