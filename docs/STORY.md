# Crucible: the story, the UI theme and the demo script

Read this before writing any user-facing copy, landing section, loading state or video shot. PLAN.md says what
we build; this file says what it should *feel* like and what the judges must walk away believing.

## The one line

> **AI writes code faster than you can understand it. Crucible proves you understand yours.**

Everything on screen serves this line. If a screen, label or video shot doesn't help prove it, cut it.

Short forms, for tight spaces:
- "Prove you understand your code."
- "Break it. Explain it. Fix it. Prove it."
- Merge gate: "Merged because you understood it, not because it compiled."

## Why it matters (Impact, 30% of the score)

- **Who:** students and early-career engineers who practise with LeetCode and ship with AI agents. That's
  us, and every CS student we know.
- **The gap:** AI made *writing* code nearly free. *Understanding* it didn't get cheaper. Interviews and
  production incidents still test understanding, and nothing helps you practise it.
- **What changes:** instead of "did it pass?", you get proof that you can explain why your code breaks,
  fix it yourself and hold the line under load, plus a replay of how you got there.
- **Where it goes next:** hiring teams screen for understanding instead of LeetCode recall, bootcamps and
  universities grade process, and teams gate AI-written PRs on a human who can defend them.

Say the problem in human terms first ("you can generate 1,000 lines in a minute and still not know why it
loses money under load"), then the product, then the tech. Never open with the tech.

## How the theme shows up in the UI

The line must be the first thing a visitor reads and the last thing a candidate sees. Concretely (Likhil owns
the components; this is the copy and intent):

| Place | What it says or shows |
|---|---|
| Landing hero | The one line as the headline, large. Sub-line: "An AI interviewer that watches how you engineer, breaks your code under real load, and makes you defend it." CTA: "Prove it" |
| Defense picker | "Bring code you didn't fully write. Let's see if you understand it." |
| Audit loading | "Muse Wonder is reading every line of your project…", not a bare spinner |
| Chaos lab | The real number, huge: "Under 200 concurrent transfers, **$8,827 disappeared**." Never a made-up number |
| Grill | "Your code broke. Explain why." The explanation stays hidden until they answer |
| Verdict | **MERGE GATE: PASS / FAIL** with the before/after numbers, and the line "Merged because you understood it, not because it compiled." |
| Report header | "Here's how you engineered, not just what you submitted." |
| Every live screen | The **Under the hood** strip (below) |

Tone: direct, confident, a little dramatic about the failure, never mocking the candidate. Real numbers
only. Every speed-up in the video is labelled.

## Under the hood: the Meta models, visible at all times

**Why:** "Use of Meta AI Tooling" (25%) asks whether we went beyond a basic integration. Judges only see the
video, so the model work has to be visible in every frame, not just in a closing slide.

**What it is:** a slim strip along the bottom of the room (both modes). Each Meta model has a chip, and a chip
lights up while that model is working and then shows what it just did:

```
UNDER THE HOOD   ● Muse Wonder  read 6 files, found 1 critical race · 44 s
                 ● Muse Spark   wrote the attack · 18 s   ○ SAM 3.1   ○ Voice   ○ Muse Image
```

- **States:** idle (dim) → working (pulsing, with the task label) → done (task, latency, then dims after a
  few seconds) → fallback (amber, "used the reference attack") → cached (the latency shown as "cached").
- **Labels are plain verbs:** "reading your project", "writing an attack", "grading your answer",
  "listening", "finding what you circled", "painting the verdict card". No model ids, no prompts, no costs on
  screen.
- **Never leaks the answer:** the strip only says *which* model did *what kind* of task, never the content.
- **In the replay too,** so the report shows when each model stepped in.

**Data (proposal, needs Srinithin + Shreyas to approve the contract change):** a new server message
`model.activity` with `{task, model_name, status: started|done|fallback|cached|failed, latency_ms}`. The
wrapper already records every call (`CallRecord` in `models/llm.py`); `main.py` passes it to the session's
runtime through `on_call`, and Defense passes the session id with each call. The MOCK fixture gets these
messages so the strip can be built on MOCK first.

## The seven Meta models, each with a visible job

| Model | Its job | Where you see it |
|---|---|---|
| Muse Wonder 1.0 | Reads the whole project in one pass (1M-token context), maps it and finds the flaws; writes the report | Topology diagram, audit, report |
| Muse Spark 1.3 | Watches every edit live, writes the targeted attack, grades the explanation | Nudges, chaos lab, grill |
| Muse Voice Transcribe | The interviewer listens: think-aloud and the spoken grill | Live transcript |
| SAM 3.1 | "Circle the flaw": finds which part of the diagram (or a paper sketch) you circled | Highlight on the diagram |
| Muse Spark Open | Open-weight fallback for grading | Strip shows it when it answers |
| Muse Image | The merge-gate card at the end | Verdict |
| Muse Code | Built Crucible; powers the in-product fix assistant, with every AI edit logged | Fix stage, "AI share" in the report |

**The surprise is the closed loop:** Wonder finds the flaw → Spark writes an attack → a sandbox breaks the
real app with real numbers → Voice hears the explanation → SAM checks what you circled → Spark grades → the
same attack re-runs to prove the fix. Every step is a different Meta model, and each one's output is the next
one's input.

## Speed is part of the story

A frozen screen loses the Demo score faster than any model upgrade wins it.
- Live roles (analyzer, interviewer, classifier, grill grading) stay on fast Spark settings.
- One-shot roles (audit, attack, report) use the strongest setting that fits their timeout (PLAN §15.1).
- Cache the audit per project, warm the sandbox before each take, and rehearse the script twice.

## The 3-minute video (v2; replaces the PLAN §20.1 draft)

| Time | Shot | What it proves |
|---|---|---|
| 0:00–0:20 | Black screen, then the line types out: "AI writes code faster than you can understand it." A real AI agent generating `bank-transfer` in seconds. "Crucible proves you understand yours." | Impact: the problem, in human terms |
| 0:20–0:30 | Landing hero, the two modes, the Under the hood strip visible | What it is |
| 0:30–1:30 | **Project Defense** (`bank-transfer`): Wonder chip lights up → the diagram builds and the node turns red → Spark writes the attack → 200 concurrent transfers stream live → "**$8,827 disappeared**" → the grill by voice → the candidate circles the flaw (SAM) → fixes it → the same attack re-runs, the line holds flat → **MERGE GATE: PASS** | The closed loop, every model visibly at work |
| 1:30–2:25 | **Live Coding Interview:** states an approach out loud → codes → skips the empty-input case → the interviewer nudges by voice → a paste gets a neutral note → submit passes | It watches *how* you engineer |
| 2:25–2:45 | Report: scrub the replay (code writing itself, synced with the transcript, nudges and model activity) | Depth and craft |
| 2:45–3:00 | The seven-model loop as one diagram, then "Crucible: prove you understand your code." Repo URL | Meta tooling, remembered |

Defense goes first now: it's the most surprising part and carries the story. Record each segment on the
deployed build at real speed; label any speed-up.

## Scoring checklist (re-read before each checkpoint)

- **Impact (30%):** does the first 20 seconds make a non-engineer care?
- **Meta tooling (25%):** is a Meta model visibly working in every shot? Is the closed loop clear?
- **Technical depth (20%):** real sandbox, real numbers, guards that never leak answers, and the replay.
- **Demo (25%):** no spinner over 3 s without a label, nothing frozen, numbers real, the take rehearsed.
