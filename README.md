# -Coding-Sectiona# ⚡ CRUCIBLE
> **The Proof-of-Engineering Gate, Chaos Sandbox & Live Staff-Engineer Grill for Vibe-Coded Software.**  
> *Built for the Meta AI Developer Hackathon (Indie Developer Track)*

---

## 🎯 Overview
AI coding agents let developers generate 1,000 lines of code in 60 seconds—but leave developers unable to explain architectural tradeoffs in technical interviews or diagnose why their code fails under production load.

**Crucible** sits between your coding agent and `git push`. Before an AI-generated feature can merge, Crucible enforces a three-stage **Proof-of-Engineering (PoE)** loop:
1. **Audit & Visualize (`Muse Wonder` + `Muse Spark` + `Muse Image`):** Scans AST diffs for concurrency hazards, $O(n^2)$ bottlenecks, and event-loop blocks, rendering live visual topology comparisons.
2. **Adversarial Chaos Lab (`Modal Sandboxes` + `Muse Glimmer 30B`):** Spins up an isolated cloud container and fires custom concurrency/exploit payloads at the endpoint, streaming real-time failure telemetry.
3. **90-Second Staff Grill (`Muse Voice Transcribe` + `SAM 3.1` + `Muse Wonder`):** Locks the PR behind a live voice and spatial-whiteboard technical defense. Once the developer diagnoses the bottleneck on the canvas, **Muse Code** executes the production refactor.

---

## 🧠 Meta AI & Partner Stack

| Layer | Model / Tool | Endpoint / Runtime | Role in Crucible |
| :--- | :--- | :--- | :--- |
| **Lead Architect & Interviewer** | `muse-wonder-1.0` | `https://api.meta.ai/v1/chat/completions` | 1M-token repo audit, tradeoff synthesis, and live Staff Defense grading. |
| **Fast AST & Exploit Generator** | `muse-spark-1.3` | `https://api.meta.ai/v1/chat/completions` | Sub-second diff scanning and generation of adversarial Python `asyncio` load scripts. |
| **Open-Weight Red-Team Agent** | `Muse-Glimmer-30B` | Hosted on **Modal GPU** (`L40S`/`A100`) | Runs autonomous fuzzing and attack loops inside the Modal environment. |
| **Topology & Tradeoff Visualizer** | `muse-image-1.0` | `POST /v1/images/generations` | Dynamically generates side-by-side fragile vs. production system diagrams. |
| **Realtime Voice Defense** | `Muse Voice Transcribe` | `wss://api.meta.ai/v1/asr/realtime` | Low-latency streaming speech-to-text during the live technical defense. |
| **Spatial Canvas & Composure** | `SAM 3.1` | `POST https://api.meta.ai/v1/responses` | Segments hand-drawn whiteboard annotations and tracks gaze/focus on webcam. |
| **Surgical Refactor Engine** | `Muse Code CLI` | `muse` subprocess / CI harness | Applies the verified production fix across the repository once defense passes. |
| **Cloud Isolation & Load Lab** | **Modal Sandboxes** | `modal.Sandbox.create()` | Ephemeral containers executing untrusted vibe-coded apps under adversarial load. |

---

## 📁 Repository Architecture (Zero-Conflict Monorepo)

```text
crucible/
├── README.md
├── CLAUDE.md                        # Strict architectural rules for Claude Code
├── MUSE.md                          # Strict architectural rules for Meta Muse Code
├── .muse/
│   └── instructions.md              # Auto-loaded instructions for `muse` CLI
├── contracts/                       # 🔒 FROZEN SHARED SCHEMAS (Single Source of Truth)
│   ├── __init__.py
│   ├── schema.py                    # Pydantic models for Backend & AI Agents
│   └── mock_session.json            # Full realistic state for offline UI & demo fallback
├── backend/
│   ├── main.py                      # FastAPI WebSocket State Bus + Mock Replay Engine
│   ├── requirements.txt
│   └── services/
│       ├── p1_auditor/              # 👤 Builder 1: Muse Spark AST + Muse Wonder Architect
│       ├── p2_chaos/                # 👤 Builder 2: Modal Sandbox + Muse Glimmer Attacker
│       └── p3_defense/              # 👤 Builder 3: Muse Voice ASR + SAM 3.1 + Muse Image
└── frontend/                        # 👤 Builder 4: Next.js 15 + Tailwind + React Flow + Monaco
    └── src/
        └── types/
            └── schema.ts            # Exact TypeScript mirror of contracts/schema.py
