# Shreyas: Project Defense + runner + infrastructure

Your slice of [PLAN.md](../PLAN.md). PLAN has the spec details; this file has the order, the handoffs and the
checklists. Team overview and the handoff calendar: [plan/README.md](README.md).

## Your job

You own the most visual part of the demo: Crucible reads a project, breaks it under load in a sandbox, grills
the candidate on why, and proves their fix. You also own the parts everyone stands on: the backend
scaffold, the runner that executes all untrusted code (both modes), MOCK mode for frontend work, CI and
deployment.

Defense reuses Srinithin's engine for the fix stage and his interviewer for grill messages, so you don't build
a second interviewer. Your job is to feed it a `RubricContext` and drive the stages around it.

## What you own

| Path | What |
|---|---|
| `Makefile`, `.env.example`, `.github/workflows/ci.yml` | Dev commands, env docs, CI |
| `backend/pyproject.toml`, `backend/Dockerfile` | Backend packaging |
| `backend/crucible/main.py`, `config.py` | App factory, routers, CORS, lifespan, settings |
| `backend/crucible/store/` | SQLite: sessions, events, reports, projects, audits |
| `backend/crucible/contracts/` | Co-owned with Srinithin; you both approve every change |
| `backend/crucible/defense/` | `controller` (`DefenseController`), `projects`, `audit`, `chaos`, `attack_writer`, `validator`, `grill`, `verify`, `verdict`, `card` (P2), `prompts/` |
| `backend/crucible/runner/` | `base.py`, `local.py`, `modal_runner.py`, `harness/` |
| `backend/crucible/mock/` | Replay engine + defense fixtures (`defense-bank-transfer`, `report-defense`) |
| `frontend/src/lib/defense.ts` | Defense-stage selectors for Likhil's views |
| Deploy config | Vercel project, Railway or Fly app, Modal app `crucible-runner` |

**Don't touch:** `engine/`, `coding/`, the rest of `models/` (Srinithin), pages and components (Likhil),
`data/` (Sharvil). If you need a change there, note it in your PR or ask the owner. Exception to agree with
Srinithin: you write `models/sam.py` and `models/image.py` for DEF-9 / DEF-10 if he's OK with it.

**Agent docs** (for Claude Code and Muse Code on this area): `backend/crucible/defense/CLAUDE.md` (area
rules; also loaded from `runner/`), `docs/defense/DEFENSE_AGENT_SPEC.txt` (Defense briefing + the decision log for
how it was reconciled with PLAN), `docs/defense/MEMORY.md` (shared working memory: file claims, status,
handoff). Team-wide: root `CLAUDE.md`, `backend/CLAUDE.md` (code style), `.claude/skills/crucible-code/`.

## Setup (Day 0, Mon Oct 26)

- [x] Claim your Meta credits (key works, 2026-10-27). **Still to do: set the $125 spend limit** (PLAN §15.3).
- [x] Modal: token connected (workspace `shreyas-sahoo-15`), credits form sent. Baseten/Fireworks: not needed (Glimmer dropped).
- [x] Python 3.12 + uv, Node ≥ 22 (pnpm runs through `npx`; Node 25+ has no corepack). Docker isn't needed locally: CI builds the image.
- [x] Review Likhil's `frontend` branch. S-0 builds on it.
- [x] Read PLAN §4, §6, §11, §12, §14.6, §19, §21 and §22.

---

## Status (end of Tue Oct 27)
- **On `main`, first pass (review fixes in #29 and the #22 plan):** S-0 (#10), store, RUN-1, RUN-3 (verified on real Modal), DEF-1..6, OPS-2 (MOCK replay
  plus a recorder), OPS-1 prep (Dockerfile, Railway config, CI Docker job, `docs/DEPLOY.md`), attack containment
  (validator + loopback-only clients + `block_network`; V7 done).
- **Open:** #17 (DEF-11 Muse fix assistant spec) and #18 (attacker prompt), both waiting on Srinithin.
- **Next:** IC1 Wed (needs Sharvil's `bank-transfer`, #11; build it from `bank-transfer-min` Wed morning if it's
  missing). Thu: `lib/defense.ts`, RUN-2. Fri: IC2 live. Sat: deploy (Railway signup was down on Oct 27; Render
  or Fly.io take the same Dockerfile).
- Working memory with the details: [docs/defense/MEMORY.md](../docs/defense/MEMORY.md).

## Handoffs

### You provide

| What | To | By | Notes |
|---|---|---|---|
| S-0: backend skeleton, `make dev`, CI, `.env.example` | Everyone | Tue Oct 27, morning | Merge Likhil's `frontend` branch first so CI covers it |
| `store/repo.py` | Srinithin (Timeline, sessions, reports) | Tue Oct 27 | Interface below |
| S-1 contracts (with Srinithin) | Everyone | Tue Oct 27 | |
| RUN-1: `Runner`, `RunRequest`, harness, LocalRunner | Srinithin (COD-3), Sharvil (`validate_problems`) | Tue Oct 27 | Types in PLAN §12 |
| LocalRunner `start_project` / `stream_exec` | Sharvil (`validate_apps`) | Wed Oct 28 | Lets him check sample apps before Modal works |
| OPS-2 skeleton → working MOCK replay | Likhil | Skeleton Tue, working Thu | Line format in PLAN §14.6; Likhil's FixtureTransport uses the same one |
| `defense-bank-transfer.jsonl`, `report-defense.jsonl` fixtures | Likhil | Thu Oct 29 | Hand-written first, recorded after IC2 |
| `lib/defense.ts` selectors | Likhil | Thu Oct 29 | Shape below |
| RUN-2: warm Modal sandbox for coding runs | Srinithin | Fri Oct 30 | IC2 |
| OPS-1: deployed frontend + backend | Everyone | Sat Oct 31 | IC3 runs on it |
| `DefenseController.report_extra()` → `DefenseExtra` | Srinithin (ENG-8) | Sat Oct 31 | DEF-7 |

### You need

| What | From | By | Until then |
|---|---|---|---|
| `models/llm.py` (ENG-3) | Srinithin | Tue Oct 27 | Call a local stub with the same signature, swap it in later |
| `bank-transfer` app + `flaws.json` | Sharvil | Wed Oct 28, noon | Write a 40-line race-condition app yourself for the first audit run |
| `ticket-drop`, `report-service`, reference attacks, `fix.patch`, validator corpus | Sharvil | Thu Oct 29 | `bank-transfer` only |
| Engine hooks: `ModeController`, `RubricContext`, `Interviewer.say()` | Srinithin | Agree Wed, built Thu | [His proposal](srinithin-engine-and-coding.md#engine-hooks-for-defense-proposed) |
| ENG-5/6 policy + interviewer | Srinithin | Fri Oct 30 | Grill questions sent as plain `interviewer.message` |
| ENG-7 voice | Srinithin | Fri Oct 30 | Text answers in the grill (that's the P0 path anyway) |
| ENG-8 ReportBuilder | Srinithin | Sat Oct 31 | — |
| OK on the PR #4 contract changes (`AuditPublic`, `GrillEval` without `score`, SAM messages) | Srinithin, Likhil | Before S-1 merges | Build S-1 from PLAN §7 as it stands after PR #4 |
| `models/sam.py`, `models/image.py`, or OK for you to write them | Srinithin | Sat Oct 31 | DEF-9 / DEF-10 are P1 / P2; skip them |
| Audit, chaos, grill and verdict views | Likhil | IC1 (plain list), Thu (full) | Check the WS output in a Python client |

### Store interface (proposed; it's yours to change)

```python
# store/repo.py
async def create_session(s: Session) -> None
async def get_session(session_id: str) -> Session | None
async def update_session(s: Session) -> None
async def append_events(session_id: str, events: list[TimelineEvent]) -> None   # batched by Timeline
async def read_events(session_id: str, kinds: set[TimelineKind] | None = None, since_seq: int = 0) -> list[TimelineEvent]
async def save_report(r: Report) -> None
async def get_report(session_id: str) -> Report | None
async def save_project(p: Project, files: dict[str, str]) -> None
async def get_project(project_id: str) -> tuple[Project, dict[str, str]] | None
async def get_audit(content_hash: str) -> AuditResult | None
async def save_audit(content_hash: str, audit: AuditResult) -> None
```

### `lib/defense.ts` (agree on the shape with Likhil)

Pure functions over his zustand session state. No fetching and no components.

```ts
export function defenseStage(phase: Phase): "audit" | "chaos" | "grill" | "fix" | "verify" | "verdict" | null;
// Label for the stepper/header, from phase + latest data (PLAN §11.2): "Broke" and "Merge approved" are data,
// not phases.
export function stageLabel(phase: Phase, runs: ChaosRun[], verdict: Verdict | null):
  "Auditing" | "Chaos run" | "Broke" | "Grill" | "Fixing" | "Verifying" | "Merge approved" | "Merge rejected" | null;
export function chaosSeries(runs: ChaosRun[], live: ChaosMetric[], runId: string):
  { t: number; inFlight: number; rps: number; p95: number; p99: number; errors: number; violations: number }[];
export function beforeAfter(runs: ChaosRun[], findingId: string):
  { baseline?: ChaosRun; verify?: ChaosRun };
export function verdictBanner(run: ChaosRun): { tone: "broke" | "held" | "error"; text: string };  // text = run.summary
export function flaggedNodeIds(audit: AuditPublic): Set<string>;
// The full Finding only exists after its grill is graded (it arrives with defense.grill.eval).
export function findingDetail(audit: AuditPublic, grill: GrillTurnWithFinding[], findingId: string):
  { public: FindingPublic; full: Finding | null };
export function nodeStatus(audit: AuditPublic, runs: ChaosRun[], nodeId: string): "ok" | "flagged" | "broke" | "verified";
```

---

## Work packages, in build order

Each one lists what to read, the files, the steps and the "done when". Hand any of them to an agent with the
prompt in [plan/README.md](README.md#using-a-coding-agent-muse-code-claude-code).

### S-0 — Scaffold
**P0 · Mon–Tue morning** · Read: PLAN §5, §6, §19.2
1. Merge Likhil's `frontend` branch (or have him open its PR first), so `frontend/` exists on `main`.
2. `backend/pyproject.toml` with uv: `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `pydantic-settings`,
   `sqlmodel`, `openai`, `websockets`, `httpx`, `modal`; dev: `ruff`, `pytest`, `pytest-asyncio`.
3. `main.py`: app factory, CORS from `CORS_ORIGINS`, lifespan, `GET /api/health` → `{ok, version, mock}`,
   and `include_router` for empty engine, coding and defense routers that each owner fills in.
4. `config.py`: `Settings` with every variable in PLAN §19.2. This is the only place secrets are read.
5. `Makefile`: `install` (uv sync + `pnpm --dir frontend install`), `dev` (uvicorn on :8000 and
   `pnpm --dir frontend dev` on :3000 together), `check` (ruff, pytest, `tsc --noEmit`, eslint, contracts
   drift), `contracts`, `validate`, `evals`, `mock` (`MOCK=1 make dev`).
6. `.env.example` from PLAN §19.2; `.gitignore` covers `.env` and `var/`.
7. CI on PRs and `main`: uv, Node 22, pnpm via corepack, `make check`.
8. `store/db.py` + `store/repo.py` (interface above).

**Done when:** `make dev` serves both apps and CI is green on `main`.

### S-1 — Contracts v1 (with Srinithin)
**P0 · Mon–Tue** · Read: PLAN §7, §8.2. Srinithin's plan has the [steps](srinithin-engine-and-coding.md#s-1--contracts-v1-with-shreyas).
Your part: review `defense.py` hard, since you'll live with it. Build it from PLAN §7.4 as updated by PR #4
(`node_id`, `FindingPublic`, `AuditPublic`, `in_flight`/`p99_ms`, `GrillEval` without `score`, the computed
fields on `GrillTurn`, `SamHighlight`, `DefenseExtra.card_url`) plus the `defense.circle` /
`defense.sam.highlight` messages.

**Settled (pending Srinithin's OK in S-1):** `ChaosPlan.p95_threshold_ms: int | None` (required, nullable,
since it's LLM output). The verdict is `broke` when it's set and p95 exceeds it. `FindingPublic.category` and
`severity` reuse the `FindingCategory` and `Severity` literals from `Finding`.

### RUN-1 — Runner protocol, harness, LocalRunner
**P0 · Tue · needs S-1** · Read: PLAN §12
**Files:** `runner/base.py`, `runner/harness/run_tests.py`, `runner/local.py`, `backend/tests/runner/`
1. `base.py`: the `Runner` protocol, `RunLimits`, `RunRequest`, `ProjectHandle` (PLAN §12).
2. The harness uses the standard library only (it's baked into a slim image). It reads `{code, function,
   cases, limits}` from stdin, executes the code in a fresh module namespace, and runs each case with a
   per-test timeout (`signal.setitimer` for sub-second limits) and a total cap. It applies the 5 comparators,
   captures stdout up to 4 KB and prints one JSON result. Syntax errors → `compile_error`.
3. `local.py`: the harness through `asyncio.create_subprocess_exec` in a temp dir. It refuses to start unless
   `RUNNER=local` and `ALLOW_LOCAL_RUNNER=1`.
4. LocalRunner `start_project` / `stream_exec` / `stop_project`: the app's entrypoint as a subprocess, with
   its requirements in an isolated environment (PLAN §12). Ship this by Wed for Sharvil.

**Tests:** each comparator; a per-test timeout; a compile error; stdout truncation; an exception inside the
candidate's code.
**Done when:** PLAN §16 RUN-1, including LocalRunner running the 3 gold problems.

### OPS-2 — Mock replay engine + fixtures
**P0 · skeleton Tue, working Thu · needs S-1** · Read: PLAN §14.6
**Files:** `mock/replay.py`, `mock/fixtures/*.jsonl`, `mock/fixtures/rest/*.json`
1. With `MOCK=1`: REST returns canned JSON; `POST /api/sessions` returns a session whose id is the scenario
   name.
2. The session socket replays `{"dt_ms", "msg"}` lines in real time. Client messages are logged, not
   answered.
3. A CI test validates every fixture line against `ServerMessage`.

**Done when:** Likhil's room runs `coding-active` and `defense-bank-transfer` from the backend with no API key.

### DEF-1 — Project store + samples API
**P0 · Wed · needs S-1, DATA-4** · Read: PLAN §11.1, §8.1, §13.2
**Files:** `defense/projects.py`, the defense router
1. At startup, load `data/defense_apps/*/` into `Project` records: files, line count, `content_hash` (sha256 of
   the sorted files), and the entrypoint and port from `crucible.json` (default 8080, so it never clashes with
   the backend's :8000 under LocalRunner).
2. `GET /api/defense/samples`. `POST /api/sessions` with `mode=defense` and `project_id`.
3. Zip upload (P1): `POST /api/defense/projects` with the §11.1 limits enforced.

### DEF-2 — Audit
**P0 · Wed (IC1: the `bank-transfer` audit renders) · needs ENG-3** · Read: PLAN §11.3
**Files:** `defense/audit.py`, `defense/prompts/audit_system.md`
1. Input: the file tree plus every file with line numbers. Wonder, `high`, 120 s → Spark 1.3 → `flaws.json`
   converted to findings (sample apps only, logged, never presented as an AI result in the demo).
2. Prompt rules the grill depends on: neutral titles and summary (the area, not the cause or fix),
   `expected_points[0]` = the root cause, every finding's `node_id` names a real node.
3. Cache by `content_hash`. Sort findings by severity, max 5. Check `node_id`s (unknown → `None`) and set
   `flagged`. Broadcast `defense.audit` as **`AuditPublic`**: no explanation, grill or fix rubric reaches the
   browser before that finding's grill is graded.
4. The recall eval: every seeded flaw found (same file, overlapping lines, same category).

**Done when:** PLAN §16 DEF-2: every seeded flaw in the 3 P0 apps is found in ≥ 2 of 3 runs.

### RUN-2 — ModalRunner for tests
**P0 · Thu · needs RUN-1** · Read: PLAN §12; check V7 first
**Files:** `runner/modal_runner.py`
1. `modal.App.lookup(MODAL_APP_NAME, create_if_missing=True)`; test image = `debian_slim(python_version="3.12")`
   plus the harness.
2. `open_session` creates one sandbox (`timeout=45*60`, `idle_timeout=10*60`) and keeps its id. `run_tests`
   execs the harness with the JSON on stdin and recreates the sandbox if it's gone.

**Done when:** PLAN §16 RUN-2: a Run on a warm sandbox returns in under 2 s (measure it and write the number
down), and the sandbox is cleaned up when the session ends.

### RUN-3 — ModalRunner for projects
**P0 · Thu · needs RUN-2, DATA-4** · Read: PLAN §12, §11.4
1. One shared project image, built at startup: `debian_slim(python_version="3.12")` + `fastapi`, `uvicorn`,
   `httpx`, `aiosqlite`, `flask` + the sample apps' requirements. Uploads with other requirements get a cached
   per-`content_hash` image on top. The demo never waits on a cold build.
2. Per run: `Sandbox.create(..., timeout=60)`, then write the project files (edited files for verify) and
   `attack.py` into the running sandbox (V7), so verify never rebuilds an image.
3. Start the entrypoint in the background, run a readiness probe on the port (≤ 10 s), exec `attack.py` and
   stream stdout, then terminate.
4. Restrict egress if the SDK supports it and loopback still works (V7).
5. Until DATA-4 lands, test against a minimal racy app in `backend/tests/fixtures/`.

### DEF-3 — AttackWriter, template, validator
**P0 · Thu · needs DEF-2** · Read: PLAN §11.4
**Files:** `defense/attack_writer.py`, `defense/validator.py`,
`runner/harness/chaos_template.py`
1. `attack_writer.py`: the `attacker` role (Spark 1.3) through Srinithin's wrapper. Finding + chaos plan +
   the relevant files + template → `AttackFunctions` (30 s); the sample's reference attack is the last fallback.
2. Fill the template by indenting the three bodies into it. Only the three bodies come from the model.
3. `validator.py`: the AST rules in §11.4 (import allowlist, forbidden names, URL literals that start with `/`
   or `BASE`, `CONCURRENCY ≤ 200`, `DURATION_S ≤ 30`). On rejection, regenerate once with the error message,
   then fail the finding.

**Done when:** PLAN §16 DEF-3: the validator rejects every script in Sharvil's bad-script corpus, and the writer
produces valid scripts for all P0 findings.

### DEF-4 — Chaos execution, metrics, verdict
**P0 · Fri (IC2: `bank-transfer` breaks live with streaming charts) · needs RUN-3, DEF-3** · Read: PLAN §4.3, §11.4
**Files:** `defense/chaos.py`
1. Per queued finding: write → validate → `start_project` → probe → exec `attack.py` → parse the JSON lines.
2. Each metric line (every 500 ms; includes `in_flight` and `p99_ms`) → `ChaosMetric` → timeline +
   `defense.chaos.metric`. Bad lines are logged as a `system` note and skipped. The final line sets the verdict:
   `broke`, `held`, or `error` on a crash or after the 60 s hard cap.
3. `ChaosRun.summary` comes from the real run ("37 of 500 transfers lost; $1,240 missing"). Never hard-code
   the numbers.

**Done when:** PLAN §16 DEF-4: every P0 sample breaks at baseline and holds with `fix.patch` applied, with live
metrics in the UI.

### DEF-5 — Grill
**P0 text (Fri), P1 voice · needs ENG-6, ENG-7** · Read: PLAN §11.5
**Files:** `defense/grill.py`
1. For each `broke` finding: rewrite `grill.question` with the real chaos summary (Spark, 6 s; fallback: the raw
   question + summary) and send it through `Interviewer.say()`.
2. A 90 s answer window. Answers arrive as final candidate `TranscriptTurn`s through
   `DefenseController.on_timeline` (voice or chat).
3. `GrillEval` (Spark, structured, 10 s): which expected points were hit, by index. **No score from the
   model.** At most one follow-up (60 s more), enforced in code. Feedback and follow-ups go through
   `Interviewer.say()`, so the leak guard applies.
4. Code computes `score` (0–10 from points hit, +1 if the SAM-circled node matches `finding.node_id`) and
   `root_cause_hit` (point 0), as in PLAN §11.5.
5. A `GrillTurn` → timeline + `defense.grill.eval`, which also carries the full `Finding` (revealed only now).

**Done when:** scoring tests cover root cause missed / hit / SAM bonus / invented point indexes, and a test
proves `defense.audit` never carries an explanation.

### DEF-6 — Fix stage, verify, verdict
**P0 · Sat · needs ENG-5, DEF-4** · Read: PLAN §11.6
**Files:** `defense/verify.py`, `defense/verdict.py`, `defense/controller.py`
1. Fix: `RubricContext.from_finding(finding, fix_patch)` → `rt.engine.attach(ctx)`. The room opens the
   finding's files in tabs.
2. Verify: `defense.verify` with the edited files → the same baseline script re-runs against them →
   `ChaosRun(kind="verify")`. If it fails, go back to fix (at most 2 extra rounds).
3. Verdict: `passed = every verify run held and avg_grill_score >= 6 and every grilled finding has
   root_cause_hit`, with reasons that quote the before/after numbers.

### OPS-1 — Deploy
**P0 · Sat · needs S-0** · Read: PLAN §19
1. `backend/Dockerfile`; Railway or Fly.io with one instance, a volume at `/data` for SQLite, and WebSockets
   enabled. `CORS_ORIGINS` = the Vercel URL. `MAX_SESSIONS_PER_IP_PER_DAY=10`.
2. Vercel for `frontend/` with `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_WS_URL`.
3. Modal tokens in the backend env.

**Done when:** PLAN §16 OPS-1: the deployed frontend runs a full coding session against the deployed backend.

### P1 and P2 (only after the P0 path is solid)
- **DEF-7 — Defense report extras** (P1 · Sun): `report_extra()` returns `DefenseExtra` (findings, chaos runs,
  grill turns, verdict); Likhil renders the before/after charts.
- **DEF-8 — Attack refine loop** (P1 · Sun): if the baseline held but the finding claims it should break, give
  the metrics back and ask for a revised attack (max 2 refinements).
- **DEF-9 — "Circle the flaw" with SAM 3.1** (P1 · Mon, **after IC3 and only with Likhil's OK** · needs DEF-5,
  Likhil's canvas pen): PLAN §11.7.
  `defense.circle` → SAM (`"hand-drawn circle"`, 5 s) → code picks the node with the largest overlap (≥ 0.3)
  → `SamHighlight` → timeline + `defense.sam.highlight`. SAM failure: no highlight, no bonus.
  *Done when* a circle around the flawed node selects it in ≥ 4 of 5 tries.
- **DEF-10 — Merge-gate card** (P2, only after both P0 paths pass the demo script twice): PLAN §11.8. Muse Image background with no text, real numbers composed
  on top, generated after the verdict in the background.
- **Refactor suggestion handoff** (P2): only if V8 confirms Muse Code has a headless mode.
- **DEF-11 — Muse fix assistant** (P1 · after IC2, Sun): PLAN §11.9. `defense/assistant.py`: `assistant.ask` →
  Spark (`assistant` role, 20 s) with the full finding, current files, chaos summary and the last verify →
  `AssistantTurn` (answer + proposed whole-file edits) → `assistant.reply`. `assistant.apply` logs accept or
  reject; the report and verdict reasons show the AI share. Only in fix/verify, max 20 asks per session.
  Needs the contract additions (SG + SS), the `assistant` role and `chars_ai` (Srinithin), and the side panel
  (Likhil).

---

## Day by day

| Day | Date | Build | End-of-day check |
|---|---|---|---|
| 0 | Mon Oct 26 | Setup, merge `frontend`, S-0, S-1 with Srinithin | Scaffold PR open |
| 1 | Tue Oct 27 | S-0 merged, store, RUN-1, OPS-2 skeleton | CI green on `main`; LocalRunner runs a gold problem |
| 2 | Wed Oct 28 | LocalRunner projects, DEF-1, DEF-2; agree on the engine hooks | **IC1**: `bank-transfer` audit renders |
| 3 | Thu Oct 29 | RUN-2, RUN-3, DEF-3, OPS-2 working, `lib/defense.ts` | Likhil runs on MOCK |
| 4 | Fri Oct 30 | DEF-4, DEF-5 (text) | **IC2**: `bank-transfer` breaks live |
| 5 | Sat Oct 31 | DEF-6, OPS-1 | Deployed |
| 6 | Sun Nov 1 | DEF-7, DEF-8, DEF-11 backend (P1); integration fixes | **IC3** + cut-line review |
| 7 | Mon Nov 2 | Reliability (cold starts, retries, timeouts); DEF-9 if IC3 is green and Likhil agrees; DEF-10 (P2) only after the demo script passes twice | Demo script passes twice |
| 8 | Tue Nov 3 | **Feature freeze 12 PM.** Bug fixes only; record demo takes | Takes recorded |
| 9 | Wed Nov 4 | Final video edit; **submit by 6 PM** | Submitted |

## What you show at each checkpoint

- **IC1 (Wed):** the `bank-transfer` audit renders in the UI. Only the model call is needed, not the runner.
- **IC2 (Fri):** the Modal runner works for both modes; `bank-transfer` breaks live with streaming charts; grill
  Q&A works in text.
- **IC3 (Sun):** both modes end-to-end on the deployed build.

## Your part of the demo (PLAN §20.1, 1:25–2:30)

`bank-transfer`: the audit node turns red → 200 concurrent transfers stream live → "BROKE: $… missing" (the
real number from the run) → the grill by voice → the candidate fixes it in the editor → verify holds →
"Merge gate: PASS". Pre-build the image and warm everything before each take.

## Risks to watch

- **Modal cold starts:** pre-build the sample images at startup; keep one warm sandbox per coding session.
- **Chaos doesn't break a sample:** Sharvil's `validate_apps` must prove break and hold for each app before it
  counts. The demo uses `bank-transfer` only.
- **Wonder slow or down:** audits are cached per project, so the demo's audit should be cached before recording.

## PR checklist

- [ ] One work package, or a clearly named part of one; branch `feat/defense-…`, `feat/runner-…` or `chore/…`
- [ ] Unit tests for the logic; fixtures updated if any message changed
- [ ] `make check` is green
- [ ] No untrusted code runs outside `Runner`; secrets are read only in `config.py`
- [ ] PLAN.md and this file updated if the plan changed; VERIFY results recorded in PLAN §23
