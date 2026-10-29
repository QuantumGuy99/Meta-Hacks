# ⚡ Crucible

**The AI technical interviewer that watches *how* you engineer, not just what you submit.**

*Built for the Meta Global AI Developer Hackathon · Indie Developer track · "Build for Your World"*

Crucible has two modes that share one live AI interviewer:

| | 🧑‍💻 **Live Coding Interview** | 🛡️ **Project Defense** |
|---|---|---|
| **You bring** | Nothing. Pick a difficulty and get an original interview problem | A project (AI-written or not) |
| **What happens** | You code in a real editor and think out loud. The interviewer watches every edit as it happens, nudges you when you skip a step or drift from your stated plan, and notices pasted code | Crucible audits the code, then **breaks it under load** in a cloud sandbox. You explain the failure out loud, fix it yourself, and Crucible re-runs the attack to prove the fix |
| **You get** | A replay of your session (code playback synced with your voice and every nudge) plus scored feedback | A pass/fail **"merge gate"** verdict, the before/after load charts, and the same replay and feedback |

> **Status (end of Tue Oct 27, hackathon day 1):** on `main`:
> - **The foundation:** shared contracts with generated TypeScript types; the Meta model wrapper, checked live
>   against the API; the session hub and timeline over WebSocket; the first analyzer → nudge path; SQLite
>   storage; dev commands; CI.
> - **Project Defense backend, first full pass:** audit → attack under load in a sandbox → grill → fix →
>   verify with the same attack → merge gate, over the WebSocket with the test app. The attack runs on real
>   Modal sandboxes. Review fixes (#22) and the real sample apps are next, so it isn't demo-ready yet.
> - **For coding interviews:** the test harness that runs candidate code.
> - **For the frontend:** MOCK replay of a recorded Defense session.
> - **Deploy:** a Docker image that CI builds and boots.
>
> The landing page and the Defense design demo are in `frontend/`. The interview room and the live Defense
> screens come next (Wed–Fri). Deployment is set for Sat Oct 31.
>
> The full build plan for humans and coding agents is **[PLAN.md](PLAN.md)**, and each teammate's part of it is
> in **[plan/](plan/README.md)**.

---

## Why we're building this

We're students who grind LeetCode and use AI coding agents every day. Two problems kept showing up:

1. **Practice tools grade the answer, but interviewers grade the process.** LeetCode tells you whether your
   code passed. It can't tell you that you started coding before stating an approach, forgot the empty-input
   case, went quiet for four minutes, or needed three hints. A human mock interviewer can, but they're expensive
   and hard to schedule.
2. **AI agents write code faster than we can understand it.** You can generate 1,000 lines in a minute and
   still be unable to explain why your endpoint loses data under 200 concurrent requests. That gap shows up in
   interviews and in production.

Crucible closes both gaps with one idea: **an AI interviewer that sees your process as it happens** (every
keystroke, every test run, every sentence you say) and holds you to what a strong engineer would do.

---

## How it works

### 🧑‍💻 Live Coding Interview
1. **Set up:** choose a difficulty and topic, **active** feedback (the interviewer steps in) or **passive**
   (it only watches and reports), and voice on or off.
2. **Clarify:** the interviewer introduces the problem. You ask clarifying questions and state your approach
   out loud, just like a real interview.
3. **Code:** you write Python in a Monaco editor. Crucible streams every edit to the interviewer, which tracks
   your progress against a per-problem rubric (steps, edge cases, target complexity). In active mode it steps
   in only at sensible moments:
   - *"You mentioned handling an empty list. I don't see that yet."* (your plan doesn't match your code)
   - *"Your loop bound on line 12 is worth a second look."* (a suspected bug, pointed at but never fixed for you)
   - *"Talk me through what you're doing here."* (you've gone silent)
   - It **notes large pastes and tab switches** in the report, neutrally and without accusing you.
4. **Test:** run the visible tests, then submit against hidden tests in a sandbox.
5. **Wrap up:** the interviewer asks about complexity and trade-offs.
6. **Report:** scores for problem solving, correctness, code quality, communication and independence (how many
   hints you needed), plus a **replay**: your code being written, synced with your transcript and every
   nudge, with "moment cards" at the turning points.

### 🛡️ Project Defense
1. **Submit:** pick a sample app or upload a small Python web project.
2. **Audit:** Muse Wonder reads the whole project in one pass, maps its structure (shown as an interactive
   diagram) and finds the riskiest flaws: race conditions, blocking I/O in async code, O(n²) hot paths.
3. **Chaos lab:** for each flaw, Muse Spark writes a targeted attack inside a fixed template, and a validator
   checks it before anything runs. Crucible boots your app and fires 200 concurrent requests at it in an
   isolated Modal sandbox, streaming the results live (*"Under 200 concurrent transfers, $1,240
   disappeared."*).
4. **The grill:** a timed interview (voice or chat) about each failure. *"Why did that happen? What would
   you change?"* The explanation of the flaw stays hidden until you've answered.
5. **Fix:** you fix the code yourself in the same live editor, with the same interviewer watching.
6. **Verify:** Crucible re-runs the exact attack. **The gate opens only if the sandbox holds and your
   explanations hold up.**

---

## Meta models we use

| Model | Where it's used in Crucible | Why this model |
|---|---|---|
| **Muse Spark 1.3** (`muse-spark-1.3`) | Live code analyzer (runs on each typing pause), interviewer replies, grill answer grading, the chaos-lab attack scripts, problem drafting | Fast, strong structured output, 1M-token context |
| **Muse Wonder 1.0** (`muse-wonder-1.0`) | Whole-project audit in Project Defense; final session reports | The strongest reasoning model; 1M context fits a whole project |
| **Muse Voice Transcribe** (`muse-voice-transcribe-1.0`) | Live think-aloud transcription and grill answers over the realtime WebSocket | Built for real-time speech; turn detection |
| **Muse Spark Open** (via Baseten) | Bulk drafting for the problem bank; failover when the main API is unavailable | Open-weight model, so we're never down when one provider is |
| **Muse Image** (`muse-image-1.0`) | Illustrations for problems (grids, trees, graphs); shareable report and merge-gate cards | Problems with diagrams are easier to understand |
| **SAM 3.1** (`sam-3.1`) | Project Defense grill: circle the broken service on the architecture diagram (or hold up a paper sketch) and Crucible finds which part you mean. *Stretch:* paper sketches in coding interviews; optional proctor check (phone in frame) | Segments any object from a short text prompt |
| **Muse Code** | Our team's coding agent for building Crucible | Faster hackathon development |

All Meta Model API calls go through `https://api.meta.ai/v1` with the OpenAI-compatible SDK.

---

## Architecture

```
┌──────────────── Browser (Next.js + TypeScript) ────────────────┐
│ Interview Room: Monaco editor ─ edit events (batched 500 ms) ──┼──┐ WebSocket (JSON)
│                 mic ─ PCM 24 kHz frames ───────────────────────┼──┼─┐ WebSocket (binary audio)
│                 interviewer panel (text + browser TTS) ◄───────┼──┤ │
│ Defense: audit diagram (React Flow) · chaos charts · grill     │  │ │
│ Report + replay (code playback synced to transcript)  ◄─ REST ─┼──┤ │
└────────────────────────────────────────────────────────────────┘  │ │
┌──────────────── Backend (Python, FastAPI) ─────────────────────┐  │ │
│ Session bus ─► Timeline (SQLite, append-only; source of truth) │◄─┘ │
│ Voice bridge ──────────────────────────────────────────────────┼◄───┘──► Muse Voice Transcribe (wss)
│ Shared interviewer engine:                                     │
│   CodeState → Analyzer (LLM suggests) → Policy (code decides) ─┼─────► Muse Spark 1.3
│   Interviewer replies · Report builder ────────────────────────┼─────► Muse Wonder 1.0
│ Coding mode: problems · test runs · integrity notes            │
│ Defense mode: ingest · audit · chaos lab · grill · verify ─────┼─────► Muse Wonder / Muse Spark
│ Runner (code execution) ───────────────────────────────────────┼─────► Modal Sandboxes
└────────────────────────────────────────────────────────────────┘
```

**Design rules**
- **Contracts first.** Every message is a Pydantic model; the TypeScript types are generated from it.
- **The LLM suggests, code decides.** The model proposes interventions; code decides when (and whether) to
  speak, enforces cooldowns and the hint ladder, and blocks anything that leaks the solution.
- **The timeline is the source of truth.** Edits, speech, runs, nudges, flags and chaos metrics are all
  timeline events. Reports and replays are built only from the timeline.
- **Every external call has a timeout and a fallback.**
- **Never hand over the answer.** Hints escalate from nudge → question → hint → concept, never code.
- **Secrets stay on the server.** The browser never sees an API key; audio is proxied through the backend.

---

## Repository layout

```
.
├── README.md · PLAN.md · LICENSE · Makefile · .env.example
├── AGENTS.md               # rules for coding agents (Muse Code reads it); areas add nested AGENTS.md files
├── plan/                    # one plan per teammate: owned paths, handoffs, build order
├── docs/defense/            # Project Defense briefing and its shared working memory
├── frontend-schematic/      # detailed frontend plan + UI rules
├── .github/workflows/       # CI: backend (ruff, pytest), frontend (eslint, tsc, Node tests), contracts drift
├── backend/                 # Python 3.12 · FastAPI · uv
│   └── crucible/
│       ├── contracts/       # 🔒 shared Pydantic schemas → generates frontend/src/types/contracts.ts
│       ├── models/          # Meta + partner model clients (LLM, ASR, image, SAM)
│       ├── engine/          # shared live interviewer (timeline, analyzer, policy, voice, report)
│       ├── coding/          # Live Coding Interview mode
│       ├── defense/         # Project Defense mode
│       ├── runner/          # code execution: Modal sandboxes (+ local dev runner)
│       ├── store/           # SQLite persistence
│       ├── datatools/       # (coming) problem generation + validation CLIs
│       └── mock/            # recorded sessions replayed for frontend development (MOCK=1)
├── data/                    # (filling in: problems and sample apps land this week)
│   ├── problems/            # original interview problems with tests, rubrics, reference solutions
│   ├── defense_apps/        # sample "vibe-coded" apps with seeded, documented flaws
│   └── evals/               # scripted sessions to test the interviewer's behavior
└── frontend/                # Next.js 16 (App Router) · React 19 · Tailwind v4 · shadcn/ui · Monaco · React Flow · Recharts
```

---

## Getting started

**Prerequisites:**
- **Python 3.12 + [uv](https://docs.astral.sh/uv/)** (`brew install uv`). uv fetches Python 3.12 for you.
- **Node 22 or later.** The Makefile uses `pnpm` if it's installed, and otherwise runs the pinned version
  through `npx` (Node 25+ no longer ships corepack).
- **A [Meta Model API](https://dev.meta.ai/docs/quickstart) key**, in `.env` as `MODEL_API_KEY`.
- **A [Modal](https://modal.com) account**, connected with `uv --directory backend run modal token new`
  (it signs in through your browser and saves the token to `~/.modal.toml`).

```bash
git clone https://github.com/QuantumGuy99/Meta-Hacks.git crucible && cd crucible
cp .env.example .env          # add MODEL_API_KEY; .env is gitignored, never commit it or paste it anywhere
make install                  # uv sync + pnpm install
make dev                      # backend on :8000, frontend on :3000 (Ctrl-C stops both)
```

Check your key with one tiny call per model role (costs a fraction of a cent):

```bash
uv --directory backend run --env-file ../.env python -m crucible.models.smoke
```

Everyday commands:

```bash
make check        # everything CI runs: ruff, pytest, eslint, tsc, Node tests, contracts drift
make test         # backend tests + the capture/replay Node tests
make contracts    # regenerate frontend/src/types/contracts.ts after changing a Pydantic contract
```

**No keys? Two ways to see Crucible run:**

```bash
MOCK=1 make dev   # the frontend gets a recorded Defense session over the real WebSocket
                  # (session id: defense-bank-transfer)
cd backend && RUNNER=local ALLOW_LOCAL_RUNNER=1 LOCAL_RUNNER_ISOLATE=0 uv run python -m crucible.defense \
  --project bank-transfer-min --apps-dir tests/fixtures/apps --duration 4 \
  --answer "The balances are read before the await and written after it, so concurrent transfers overwrite each other. Make it atomic with a lock."
                  # the whole Defense pipeline in the terminal: break → grill → fix → verify → merge gate
```

Coming soon: `make validate` (checks every problem and sample app in `data/`) and `make evals` (scripted
sessions through the real models; costs credits). Deploying: see [docs/DEPLOY.md](docs/DEPLOY.md). It stays
on free tiers and credits.

**Working with coding agents:** Muse Code reads [AGENTS.md](AGENTS.md) (team rules). Areas can add their own
rules in a nested `AGENTS.md`, as Project Defense does in `backend/crucible/defense/AGENTS.md`. File templates
are in [docs/agents/code-templates.md](docs/agents/code-templates.md).

---

## Team

| Person | GitHub | Owns | Plan |
|---|---|---|---|
| **Srinithin Ganesh** | [@Srinithin551](https://github.com/Srinithin551) | Live Coding Interview backend + the shared interviewer engine (analyzer, policy, voice, reports) | [plan](plan/srinithin-engine-and-coding.md) |
| **Shreyas Sahoo** | [@ss15-debug](https://github.com/ss15-debug) | Project Defense backend (audit, chaos lab, grill, verify), the code runner, scaffold, CI and deployment | [plan](plan/shreyas-defense-and-runner.md) |
| **Likhil Gudipati** | [@lgudip-01](https://github.com/lgudip-01) | Frontend for both modes: interview room, defense flow, report and replay | [plan](plan/likhil-frontend.md) |
| **Sharvil Talware** | | Data for both modes: the problem bank, sample defense apps, evals | [plan](plan/sharvil-data.md) |

---

## Built during the hackathon

Everything in this repository was written during the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026).
The idea of an AI interviewer that gives feedback as you go is inspired by our earlier project
[Osiris](https://github.com/Srinithin551/Osiris) (HackRU 2026, spoken mock interviews); **no Osiris code was
reused.** All interview problems are original and written for Crucible; none are copied from LeetCode or other
problem sites.

## License

[MIT](LICENSE)
