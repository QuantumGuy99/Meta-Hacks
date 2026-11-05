# Ares: submission text

Ready to paste into the submission form. Every file, model and claim below was checked against the code on
`main` (model roles in `backend/crucible/models/registry.py`).

## Elevator pitch

Ares is a voice-enabled AI technical interviewer and adversarial project-defense platform. It counters
superficial "vibe coding": it audits a candidate's uploaded project, runs targeted attacks against it in an
isolated Modal sandbox, and grills the developer live by voice, alongside a real-time coding interview room
and a replayable session timeline. Its intelligence runs on Meta's Muse models, with ElevenLabs for the
interviewer's voice.

## The problem it solves

Software interviews and project evaluations break down in two ways:

1. **"Vibe coding" and the portfolio verification gap.** With AI code generators, anyone can assemble an
   impressive repository without understanding its architecture, edge cases or failure modes. Static code
   reviews and resume screens can't tell whether a developer understands the code they claim to have written.
2. **Brittle, unrealistic assessments.** Automated coding platforms test memorized algorithms in a silent text
   box. They don't evaluate how an engineer communicates under pressure, defends trade-offs, debugs a live
   failure or reasons through spoken questions.

Ares moves technical evaluation from a static code submission to active, adversarial verification and a live,
spoken dialogue.

## What it does

A Next.js frontend and an event-driven FastAPI backend (`main.py`) put the candidate in a real-time room
(`LiveRoom.tsx`, `LiveDefense.tsx`) connected over REST and WebSockets, with two-way voice (`engine/voice.py`).
Two modes share one interviewer engine:

### 1. Project Defense
- **Audit** (`defense/projects.py`, `defense/audit.py`): the candidate uploads a project through the Defense
  API (`defense/router.py`). **Muse Wonder 1.0** reads the whole project in one pass, maps its architecture
  and finds the riskiest flaws.
- **Attack in a sandbox** (`defense/attack_writer.py`, `runner/modal_runner.py`): **Muse Spark 1.3** writes a
  targeted attack for each flaw inside a fixed template; a validator checks it before anything runs, and it
  fires (for example) 200 concurrent requests at the real app in an isolated Modal sandbox.
- **Grill, fix, verify, verdict** (`defense/grill.py`, `defense/controller.py`, `defense/pipeline.py`,
  `defense/verdict.py`): the interviewer asks, by voice, why the code broke under that attack. **Two Meta
  models grade each answer** (Muse Spark and Muse Wonder) and a point counts only if both agree. The candidate
  fixes the code in the editor, the same attack re-runs, and the **merge verdict is computed in Python** from
  the verify runs and grill scores, never by a model.

### 2. Live Coding Interview
- **Problems and tests** (`coding/problems.py`, `coding/tests.py`): original problems, run against visible and
  hidden tests in the sandbox, in Python, Java, C++ or C.
- **Live analysis and a Socratic interviewer** (`engine/analyzer.py`, `engine/interviewer.py`, orchestrated by
  `engine/hub.py` and `coding/session.py`): Muse Spark reads the code on each typing pause, and the
  interviewer nudges, asks and escalates hints without ever giving away the answer (a leak guard checks every
  line it says).

### 3. Voice, sandboxing and replay
- **Voice** (`models/asr.py`, `models/tts.py`): microphone audio streams through the backend's voice bridge to
  **Muse Voice Transcribe** for real-time speech-to-text; the interviewer's lines are spoken by ElevenLabs,
  with the browser voice as fallback.
- **Timeline and report** (`engine/timeline.py`, `engine/report.py`, `ReportView.tsx`): every edit, test run,
  attack result and spoken word is a typed event (`contracts/common.py`) on one timeline. At the end, Muse
  Wonder writes the report and the candidate gets scores plus a full replay of the session.

## How we use Meta's models

Every model call goes through one gateway (`models/llm.py`) that applies a timeout and a fallback to each call;
a per-IP session cap in the backend config guards spend.

| Model | Job in Ares |
|---|---|
| **Muse Wonder 1.0** | Audits the whole project in one pass; second grader of every grill answer; writes the final report |
| **Muse Spark 1.3** | Live code analyzer on each typing pause; interviewer replies; writes the attack scripts; first grader of grill answers |
| **Muse Voice Transcribe** | Real-time speech-to-text for think-aloud and the spoken grill |

### Why Meta's models
Ares needs two things at once: **deep, multi-file code reasoning** to find what breaks a project, and **fast
turn-taking** to hold a natural spoken interview.
- **Deep reasoning (Muse Wonder):** reading a whole repository in one pass (1M-token context, no chunking) and
  finding a real flaw, such as a race condition that loses money under load.
- **Speed (Muse Spark):** at minimal reasoning effort the live analyzer answers in about 4 seconds (8–12 s at
  low), fast enough to follow every typing pause.
- **Speech (Muse Voice Transcribe):** final transcripts arrive 0.1–0.2 s after the speaker stops, so the
  interviewer can answer a spoken explanation right away.
- **Structured output:** every stage returns schema-checked structured output, so the pipeline never parses
  free text. **The model suggests, code decides:** scores, phase changes and the merge verdict are Python.

## Short version (character-limited boxes)

Ares runs on the Meta Model API through one gateway (`llm.py`, a timeout and fallback on every call) and
Muse Voice Transcribe (`asr.py`). In Project Defense, Muse Wonder 1.0 audits the whole uploaded project
(`audit.py`), Muse Spark 1.3 writes targeted attacks (`attack_writer.py`) that run in a Modal sandbox, and the
candidate is grilled by voice on why it broke (`grill.py`): Spark and Wonder both grade each answer, and a
point counts only if they agree. The merge verdict (`verdict.py`) is computed in code, not by a model. In the
Live Coding Interview, Muse Spark analyzes the code on every typing pause (`analyzer.py`) and drives a
Socratic interviewer (`interviewer.py`), and Muse Wonder writes the final report (`report.py`). Muse Voice
Transcribe turns live speech from our WebSocket voice bridge (`voice.py`) into text in real time, so both modes
are spoken conversations, not text boxes.
