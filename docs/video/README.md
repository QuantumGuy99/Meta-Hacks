# Ares demo video: the full guide

Everything the team needs to finish the 3-minute demo video: what the judges look for, the format, what to
show second by second, what to say, how to record and how to build the final file.

**Preview:** [`ares-demo-preview.mp4`](ares-demo-preview.mp4) (2:58). Its hook, "who it's for", technical
section and end card are final. Its four product segments are **placeholders** (striped slates with a
running clock) until we drop in live screen recordings. To watch it, open the file on GitHub and click
**View raw** or **Download**.

**Deadline:** submission closes at **9 PM ET, Wed Nov 4**.

---

## 1. How we're judged, and what that means for the video

The hackathon judges in three stages:

1. **Stage 1, pass/fail:** does the project fit the theme ("Build for Your World"), and does it really use
   Meta's models? → Say both out loud in the first 30 seconds, and name a Meta model each time one acts.
2. **Stage 2, scored 0–10 per criterion.** Weights (from [STORY.md](../STORY.md)): **Impact 30%, Use of
   Meta AI tooling 25%, Demo 25%, Technical depth 20%.** Judges most likely see only the video, so anything we
   don't show doesn't count.
3. **Stage 3, the top 5 per track:** final-round judges **watch the video live in a room** and rank it on
   the same rubric. → Burn in captions (room audio is often bad), zoom the browser to 125–150% so text reads
   on a projector, and make the big moments ("$8,827 disappeared", "MERGE GATE: PASS") fill the screen.

What each criterion needs on screen:

| Criterion | What the video has to prove |
|---|---|
| Impact (30%) | The first 20 seconds make a non-engineer care. Problem in human terms first, never the tech first |
| Meta tooling (25%) | A Meta model is visibly working in every shot, and the closed loop (one model's output is the next one's input) is clear |
| Demo (25%) | It's real and smooth: no spinner over 3 s without a label, nothing frozen, real numbers, a rehearsed take |
| Technical depth (20%) | The real sandbox, real numbers, guards that never leak answers, the replay, and a short "under the hood" section |

### What the research on winning demo videos says

There's no published analysis of winning Meta or Devpost videos, but organizer and winner advice agrees:
open with the problem within ~20 seconds, framed around a real person; spend about half the video on the
working product; make the sponsor's API visibly part of the demo; explain the hard part; and **respect the
time limit** (some judges are told to stop at 3:00). Production polish matters less than a clear, real
product. At Meta's own hackathons (LlamaCon, Llama Impact) finalists demoed live, and winners showed one
concrete, working use of the model.

---

## 2. The format (2:58)

| Time | Segment | Length | Source |
|---|---|---|---|
| 0:00–0:20 | **Hook** | 20 s | rendered (`scenes.html`) ✅ |
| 0:20–0:30 | **Who it's for** | 10 s | the real landing page, captured ✅ |
| 0:30–1:30 | **Project Defense** | 60 s | 🎥 record → `clips/defense.mp4` |
| 1:30–1:40 | **Defense report** | 10 s | 🎥 record → `clips/defense_report.mp4` |
| 1:40–2:20 | **Live Coding Interview** | 40 s | 🎥 record → `clips/coding.mp4` |
| 2:20–2:32 | **Coding report + replay** | 12 s | 🎥 record → `clips/coding_report.mp4` |
| 2:32–2:52 | **Technical: under the hood** | 20 s | rendered ✅ |
| 2:52–2:58 | **End card** | 6 s | rendered ✅ |

Why this shape:
- **Defense comes first:** it's the most surprising part and carries the story.
- **Meta in the hook is one line at the end** ("built on Meta's Muse models"), not the opener. Stage 1 is
  won by naming a model each time one acts during the product clips.
- **The two reports show different things,** so we don't spend 10 seconds repeating the replay: the Defense
  report shows before/after numbers and grill scores; the coding report shows the scores and the replay.
- **If a product segment needs more time, take it from the technical section,** never from the hook.

---

## 3. What each segment shows

### 0:00–0:20 Hook (done)
Black screen, "AI writes code faster than you can understand it." types out. An AI agent streams the
`bank-transfer` code in under 4 seconds ("happy path passes ✓"), the risky lines light up red, and the
question appears: "It passes the happy path. Can you explain why it loses money under load?" Then
"**Ares_** proves you understand your code." with the chips "Built on Meta's models: Muse Wonder 1.0 ·
Muse Spark 1.3 · Muse Voice Transcribe". The code is labelled "illustration".

### 0:20–0:30 Who it's for (done)
The real landing page ("Practice Tools Grade Answers. Ares Grades How You Engineer.", its live code panel and
the "6 Meta models in the loop" stats) with a banner: "For students and early-career engineers who prep for
interviews and ship with AI agents". This is our theme-fit line.

### 0:30–1:30 Project Defense (record, 60 s)

| Time | Beat |
|---|---|
| 0:30–0:38 | Pick `bank-transfer` → Start. Muse Wonder audits (label any speed-up) |
| 0:38–0:48 | The topology diagram builds; the flawed node turns red |
| 0:48–1:00 | Muse Spark writes the attack → 200 concurrent transfers stream live → the real dollar loss, big |
| 1:00–1:14 | The grill by voice: the interviewer's question, your spoken answer, the follow-up |
| 1:14–1:30 | Fix it in the editor → Verify re-runs the same attack → the line holds → **MERGE GATE: PASS** |

### 1:30–1:40 Defense report (record, 10 s)
Before/after load numbers and the grill scores (1:30–1:35), then how much of the fix was yours vs. the fix
assistant (1:35–1:40).

### 1:40–2:20 Live Coding Interview (record, 40 s)

| Time | Beat |
|---|---|
| 1:40–1:48 | Setup (active feedback, voice on) → the interviewer presents the problem |
| 1:48–1:58 | State your approach out loud, start coding |
| 1:58–2:08 | Skip the empty-input case → the interviewer nudges by voice |
| 2:08–2:14 | Paste a block → the neutral paste note appears |
| 2:14–2:20 | Run, then Submit → hidden tests pass |

Optional, if there's a second: show the language picker (Python, Java, C++, C).

### 2:20–2:32 Coding report + replay (record, 12 s)
The scores (problem solving, correctness, communication, independence) for 5 s, then scrub the replay: the
code writing itself, synced with the transcript and the nudges.

### 2:32–2:52 Technical: under the hood (done)
"One closed loop. A Meta model at every step.": **Muse Wonder** reads the project and finds the flaw →
**Muse Spark** writes a targeted attack (validated before it runs) → the **Modal sandbox** fires 200
concurrent requests → **Muse Voice Transcribe** hears your explanation → **Muse Spark + Muse Wonder** grade
it (a point counts only if both agree) → the **same attack re-runs** to prove the fix. Then the coding mode
line, and three rules: *the model suggests, code decides* · *never hands over the answer (leak guard)* ·
*every call has a timeout and a fallback; untrusted code runs only in the sandbox.*

### 2:52–2:58 End card (done)
"Ares_ / Prove you understand your code." The live URL (add it, see §6), the repo URL, the four names and
"Built during the Meta Global AI Developer Hackathon · Indie Developer track".

---

## 4. What to say: the voiceover script

About 2.5 words per second. **Leave the voiceover silent where the clip's own sound carries the moment**
(the interviewer's questions, your answers): `build.py` keeps each recording's sound and mixes the
voiceover on top.

Record **one file per line**, named by its start time (`0048.m4a` = the line at 0:48), so it can be placed
exactly. "Max" is the time before the next line starts; stay under it.

| File | Starts | Max | On screen | Say |
|---|---|---|---|---|
| `0000` | 0:00 | 15 s | Text types out, the AI agent writes the code | AI writes code faster than we can understand it. An agent builds this transfer API in seconds, and it passes the happy path. But could you explain why it loses money under load? |
| `0015` | 0:15 | 5 s | "Ares_ proves you understand your code" | Ares, built on Meta's Muse models, proves you understand your code. |
| `0020` | 0:20 | 10 s | The landing page | We're students who prep for interviews and ship with AI agents every day. Ares grades how you engineer, not just your answer. |
| `0030` | 0:30 | 18 s | Audit, the diagram, the red node | In Project Defense, you bring code, even code your AI wrote. Muse Wonder reads the whole project in one pass, maps it, and flags the riskiest flaw: a race condition in money transfers. |
| `0048` | 0:48 | 12 s | The attack streams, the dollar loss | Muse Spark writes a targeted attack, and Ares fires two hundred concurrent transfers at the real app in a sandbox. Thousands of dollars just disappeared. |
| — | 1:00–1:09 | — | The grill | *(silent: the interviewer's question and your spoken answer play)* |
| `0109` | 1:09 | 5 s | Grill grading | Muse Voice Transcribe hears me, and two Meta models grade it. |
| `0114` | 1:14 | 16 s | Fix, verify, merge gate | A point counts only if both agree. Then I fix it myself. Ares re-runs the exact same attack. It holds. Merge gate: pass. |
| `0130` | 1:30 | 10 s | Defense report | The report shows the before and after, my grill scores, and how much of the fix was mine. |
| `0140` | 1:40 | 8 s | Coding setup, the problem appears | The Live Coding Interview works the same way. I explain my approach out loud, and Muse Spark follows every edit. |
| — | 1:48–2:03 | — | Approach out loud, coding, the nudge | *(silent: your spoken approach, then the interviewer's nudge)* |
| `0203` | 2:03 | 5 s | The fix for the empty case | It caught the missing empty case, without giving me the answer. |
| `0208` | 2:08 | 12 s | Paste note, Run, Submit | A paste gets a neutral note, not an accusation. Submit runs the hidden tests in the sandbox. All pass. |
| `0220` | 2:20 | 12 s | Coding report, replay | Muse Wonder writes the report: scores for how I solved it, and a replay of my code, synced with everything I said. |
| `0232` | 2:32 | 20 s | The closed loop, the three rules | Under the hood, it's one closed loop with a Meta model at every step. The model suggests, code decides: scores and verdicts are computed in Python, and a leak guard checks every line, so the interviewer never hands over the answer. |
| `0252` | 2:52 | 6 s | End card | Ares. Prove you understand your code. |

Tone: direct, confident, a little dramatic about the failure, never mocking the candidate.

---

## 5. How to record the four product segments

Record on a machine with the real `.env` (it's gitignored, so only on your laptop).

1. Run `make dev`, or use the deployed site (open it once first; the backend sleeps when idle).
2. **Warm up:** run one Defense audit on `bank-transfer` before the take, so the audit is cached and the
   sandbox is warm.
3. Chrome full screen (F11), browser zoom **125%**, 1920×1080, bookmarks bar hidden, notifications off.
4. Record with OBS (or QuickTime on Mac, Win+G on Windows) **with system audio on**, so the interviewer's
   voice is in the clip. Use a decent mic for your spoken answers.
5. Record each segment **twice** and keep the better take.
6. Trim each take to its slot and save it under the slot's name, e.g.
   `ffmpeg -ss 00:01:05 -to 00:02:05 -i raw.mov docs/video/clips/defense.mp4`.

### Rules for every shot
- **Real flows, real speed, real numbers.** Never MOCK mode, never the scripted `/demo` rooms (PLAN §2: no
  fake or mocked flows in the video). A judge who opens the repo will check.
- **No dead air.** No spinner over ~3 s without a label. If you shorten a wait (the audit), show a label such
  as "audit: 44 s, shortened". Never hide a cut.
- **Don't show SAM "circle the flaw"**: it only exists in the scripted demo room, not the live rooms.
- **Name models by their job** ("Muse Wonder reads the whole project"). No model ids, prompts, costs or long
  terminal logs on screen.
- **Mention ElevenLabs once, as voice output only:** it only reads the interviewer's lines aloud, and every
  decision stays on Meta models.

---

## 6. Building the final video

The rendered segments are committed in `build/`, so you only need **Python 3 and ffmpeg**
(`brew install ffmpeg` / `winget install ffmpeg`).

```bash
git fetch origin claude/happy-shannon-oapm70 && git checkout claude/happy-shannon-oapm70
python3 docs/video/build.py        # → docs/video/out/ares-demo.mp4
```

Put these in `docs/video/` and rebuild (about a minute each time):

| File | What it does |
|---|---|
| `clips/defense.mp4`, `clips/defense_report.mp4`, `clips/coding.mp4`, `clips/coding_report.mp4` | Replace the placeholders (mp4/mov/webm/mkv). Scaled to 1920×1080 @ 30 fps; only the first N seconds are used (N = slot length); a shorter clip holds its last frame. Each keeps its own sound |
| `vo_lines/<MMSS>.m4a` (or `.wav`/`.mp3`) | One file per voiceover line (§4). Each is trimmed, levelled, placed at its start time and checked against its limit (up to 10% too long is sped up; more is flagged). Captions are generated from the script; `vo_lines/<MMSS>.txt` overrides a line's caption |
| `vo.wav` (or `.m4a`/`.mp3`) | Alternative: one voiceover track mixed from 0:00 (takes priority over `vo_lines/`) |
| `captions.srt` | Burned-in captions (recommended for the live final round) |

To put the live URL on the end card (needs Node + Playwright and the frontend running on :3000):

```bash
cd frontend && pnpm dev
node docs/video/render.js --live https://your-app-url
```

### Submission checklist
- [ ] Final video is **under 3:00** (the timeline is 2:58).
- [ ] All four placeholders replaced with live recordings, no slate left.
- [ ] Voiceover added; captions burned in if there's time.
- [ ] Uploaded to YouTube as **unlisted**; the link opens in a private window without sign-in. Uploads can
  take a while, so allow an hour.
- [ ] Repo public, deployed URL works from a clean browser (PLAN §20.2).

---

## 7. Files here

| File | What it is |
|---|---|
| `README.md` | This guide |
| `ares-demo-preview.mp4` | The current preview cut (placeholders in the product segments) |
| `scenes.html` | The hook, technical loop, end card and slates (frame-accurate: `window.seek(scene, t)`) |
| `render.js` | Renders those into `build/` and captures the landing page with the "who it's for" banner |
| `build.py` | Assembles `out/ares-demo.mp4` from `build/`, `clips/`, `vo.*` and `captions.srt` |
| `build/` | The rendered segments (committed) |

`out/`, `clips/`, `vo.*` and `captions.srt` are gitignored. Share final recordings outside git (they're large).
