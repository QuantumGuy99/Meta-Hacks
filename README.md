# ⚡ Crucible

**The AI technical interviewer that watches *how* you engineer, not just what you submit.**

*Built for the Meta Global AI Developer Hackathon · Indie Developer track · "Build for Your World"*

Crucible has two modes that share one live AI interviewer:

| | 🧑‍💻 **Live Coding Interview** | 🛡️ **Project Defense** |
|---|---|---|
| **You bring** | Nothing. Pick a difficulty and get an original interview problem | A project (AI-written or not) |
| **What happens** | You code in a real editor and think out loud. The interviewer watches every edit as it happens, nudges you when you skip a step or drift from your stated plan, and notices pasted code | Crucible audits the code, then **breaks it under load** in a cloud sandbox. You explain the failure out loud, fix it yourself, and Crucible re-runs the attack to prove the fix |
| **You get** | A replay of your session (code playback synced with your voice and every nudge) plus scored feedback | A pass/fail **"merge gate"** verdict, the before/after load charts, and the same replay and feedback |

> **Status:** planning and scaffolding (hackathon day 0). The full build plan for humans and coding agents is in
> **[PLAN.md](PLAN.md)**, and each teammate's part of it is in **[plan/](plan/README.md)**. The frontend scaffold
> and landing page are on the `frontend` branch.

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
3. **Chaos lab:** for each flaw, an AI agent writes a targeted load script. Crucible runs your app and the
   attack in an isolated Modal sandbox and streams the results live (*"Under 200 concurrent transfers,
   $1,240 disappeared."*).
4. **The grill:** a timed voice interview about each failure. *"Why did that happen? What would you change?"*
5. **Fix:** you fix the code yourself in the same live editor, with the same interviewer watching.
6. **Verify:** Crucible re-runs the exact attack. **The gate opens only if the sandbox holds and your
   explanations hold up.**

---

## Meta models we use

| Model | Where it's used in Crucible | Why this model |
|---|---|---|
| **Muse Spark 1.3** (`muse-spark-1.3`) | Live code analyzer (runs on each typing pause), interviewer replies, grill answer grading, problem drafting | Fast, strong structured output, 1M-token context |
| **Muse Wonder 1.0** (`muse-wonder-1.0`) | Whole-project audit in Project Defense; final session reports | The strongest reasoning model; 1M context fits a whole project |
| **Muse Voice Transcribe** (`muse-voice-transcribe-1.0`) | Live think-aloud transcription and grill answers over the realtime WebSocket | Built for real-time speech; turn detection |
| **Muse Glimmer** (open weights, 30B) | The chaos-lab attack agent: writes, runs and refines load scripts | Open weights we host and control; built for tool-calling agents |
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
│ Defense mode: ingest · audit · chaos lab · grill · verify ─────┼─────► Muse Wonder / Muse Glimmer
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
├── plan/                    # one plan per teammate: owned paths, handoffs, build order
├── frontend-schematic/      # detailed frontend plan + UI rules
├── backend/                 # Python 3.12 · FastAPI · uv
│   └── crucible/
│       ├── contracts/       # 🔒 shared Pydantic schemas → generates frontend/src/types/contracts.ts
│       ├── models/          # Meta + partner model clients (LLM, ASR, image, SAM, Glimmer)
│       ├── engine/          # shared live interviewer (timeline, analyzer, policy, voice, report)
│       ├── coding/          # Live Coding Interview mode
│       ├── defense/         # Project Defense mode
│       ├── runner/          # code execution: Modal sandboxes (+ local dev runner)
│       ├── store/           # SQLite persistence
│       ├── datatools/       # problem generation + validation CLIs
│       └── mock/            # fixture replay for frontend development (MOCK=1)
├── data/
│   ├── problems/            # original interview problems with tests, rubrics, reference solutions
│   ├── defense_apps/        # sample "vibe-coded" apps with seeded, documented flaws
│   └── evals/               # scripted sessions to test the interviewer's behavior
└── frontend/                # Next.js 16 (App Router) · React 19 · Tailwind v4 · shadcn/ui · Monaco · React Flow · Recharts
```

---

## Getting started

> These commands work once the Day 0 scaffold lands (see [PLAN.md §16](PLAN.md#16-work-packages)).

**Prerequisites:** Python 3.12 + [uv](https://docs.astral.sh/uv/), Node 22+ with pnpm (`corepack enable`), a
[Meta Model API](https://dev.meta.ai/docs/quickstart) key, and a [Modal](https://modal.com) account
(`modal token new`).

```bash
git clone https://github.com/QuantumGuy99/Meta-Hacks.git crucible && cd crucible
cp .env.example .env          # add MODEL_API_KEY and the Modal tokens
make install                  # uv sync + pnpm install
make dev                      # backend on :8000, frontend on :3000
```

Frontend work without API keys: `MOCK=1 make dev` replays recorded sessions over the same WebSocket.

```bash
make check        # ruff + pytest + tsc + eslint + contracts drift check
make contracts    # regenerate frontend/src/types/contracts.ts from the Pydantic schemas
make validate     # validate every problem and sample app in data/
make evals        # replay scripted sessions through the interviewer (calls the API; costs credits)
```

---

## Team

| Person | Owns | Plan |
|---|---|---|
| **Srinithin Ganesh** | Live Coding Interview backend + the shared interviewer engine (analyzer, policy, voice, reports) | [plan](plan/srinithin-engine-and-coding.md) |
| **Shreyas Sahoo** | Project Defense backend (audit, chaos lab, grill, verify) + the code runner and deployment | [plan](plan/shreyas-defense-and-runner.md) |
| **Likhil Gudipati** | Frontend for both modes: interview room, defense flow, report and replay | [plan](plan/likhil-frontend.md) |
| **Sharvil Talware** | Data for both modes: the problem bank, sample defense apps, evals | [plan](plan/sharvil-data.md) |

---

## Built during the hackathon

Everything in this repository was written during the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026).
The idea of an AI interviewer that gives feedback as you go is inspired by our earlier project
[Osiris](https://github.com/Srinithin551/Osiris) (HackRU 2026, spoken mock interviews); **no Osiris code was
reused.** All interview problems are original and written for Crucible; none are copied from LeetCode or other
problem sites.

## License

[MIT](LICENSE)
