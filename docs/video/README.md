# Ares demo video: the full guide

Everything the team needs to finish the 3-minute demo video: what the judges look for, the format, what to
show second by second, what to say, how to cut the demo recordings and how to build the final file.

**Preview:** [`ares-demo-preview.mp4`](ares-demo-preview.mp4) (2:56). The problem statement, the intro, the
technical section and the end card are final, with the voiceover, captions and music. The two demo segments
are **placeholders** (striped slates with a running clock) until we drop in the live recordings. To watch it,
open the file on GitHub and click **View raw** or **Download**.

**Deadline:** submission closes at **9 PM ET, Wed Nov 4**.

---

## 1. How we're judged, and what that means for the video

1. **Stage 1, pass/fail:** does the project fit the theme ("Build for Your World"), and does it really use
   Meta's models? → The video opens with the problem we have ourselves, and names a Meta model each time one acts.
2. **Stage 2, scored 0–10 per criterion.** Weights (from [STORY.md](../STORY.md)): **Impact 30%, Use of
   Meta AI tooling 25%, Demo 25%, Technical depth 20%.** Judges most likely see only the video.
3. **Stage 3, the top 5 per track:** judges **watch the video live in a room**. → Captions are burned in, the
   browser is zoomed to 125% when recording, and the big moments fill the screen.

| Criterion | What the video has to prove |
|---|---|
| Impact (30%) | The first seconds are a problem a non-engineer gets, before any product |
| Meta tooling (25%) | A Meta model is visibly working in every shot; the closed loop is clear |
| Demo (25%) | It's real and smooth: real numbers, nothing frozen, every speed-up labelled |
| Technical depth (20%) | Real sandbox, real numbers, guards that never leak answers, the replay, "under the hood" |

Research on winning demo videos agrees: open with the problem within ~20 seconds, spend about half the video
on the working product, make the sponsor's API visible, explain the hard part, and stay under the time limit.

---

## 2. The format (2:56)

| Time | Segment | Source |
|---|---|---|
| 0:00–0:10 | **Problem 1:** practice sites grade the answer, interviewers grade how you think | rendered ✅ (needs the new line `0000`) |
| 0:10–0:20 | **Problem 2:** AI writes code faster than we can understand it | rendered ✅ |
| 0:20–0:30 | **The answer:** Ares, built on Meta's models; who it's for (landing page) | rendered ✅ |
| 0:30–1:30 | **Project Defense demo, including its report** | 🎥 `clips/defense.mp4` (cut to 60 s, §5) |
| 1:30–2:30 | **Live Coding Interview demo, including its report** | 🎥 `clips/coding.mp4` (cut to 60 s, §5) |
| 2:30–2:50 | **Technical: under the hood** | rendered ✅ |
| 2:50–2:56 | **End card** | rendered ✅ |

---

## 3. What to say: the voiceover

Each line is its own file in `vo_lines/`, named by its start time. **14 are recorded. Only `0000` is new.**
Record it, save it as `vo_lines/0000.m4a`, and keep it under **9.5 seconds** (about 25 words at a normal pace).

| File | Starts | Status | Say |
|---|---|---|---|
| **`0000`** | 0:00 | 🎙️ **record this** | Coding practice sites only check if your answer passes. But real interviewers grade how you think: your approach, your edge cases, how you explain it. |
| `0010` | 0:10 | ✅ recorded | AI writes code faster than we can understand it. An agent builds this transfer API in seconds, and it passes the happy path. But could you explain why it loses money under load? |
| `0019` | 0:19 | ✅ | Ares, built on Meta's Muse models, proves you understand your code. |
| `0023` | 0:23 | ✅ | We're students who prep for interviews and ship with AI agents every day. Ares grades how you engineer, not just your answer. |
| `0030` | 0:30 | ✅ | In Project Defense, you bring code, even code your AI wrote. Muse Wonder reads the whole project in one pass, maps it, and flags the riskiest flaw: a race condition in money transfers. |
| `0042` | 0:42 | ✅ | Muse Spark writes a targeted attack, and Ares fires two hundred concurrent transfers at the real app in a sandbox. |
| — | 0:52–1:02 | — | *(silent: the interviewer's grill question and your spoken answer, from the recording)* |
| `0102` | 1:02 | ✅ | Muse Voice Transcribe hears me, and two Meta models grade it. |
| `0106` | 1:06 | ✅ | A point counts only if both agree. Then I fix it myself. Ares re-runs the exact same attack. It holds. Merge gate: pass. |
| `0118` | 1:18 | ✅ | The report shows the before and after, my grill scores, and how much of the fix was mine. |
| `0130` | 1:30 | ✅ | The Live Coding Interview works the same way. I explain my approach out loud, and Muse Spark follows every edit. |
| — | 1:38–2:00 | — | *(silent: you stating your approach out loud, then the interviewer's spoken nudge, from the recording)* |
| `0200` | 2:00 | ✅ | It caught the missing empty case, without giving me the answer. |
| `0205` | 2:05 | ✅ | A paste gets a neutral note, not an accusation. Submit runs the hidden tests in the sandbox. All pass. |
| `0215` | 2:15 | ✅ | Muse Wonder writes the report: scores for how I solved it, and a replay of my code, synced with everything I said. |
| `0230` | 2:30 | ✅ | Under the hood, it's one closed loop with a Meta model at every step. The model suggests, code decides: scores and verdicts are computed in Python, and a leak guard checks every line, so the interviewer never hands over the answer. |
| `0250` | 2:50 | ✅ | Ares. Prove you understand your code. |

After adding or re-recording a line: make its text in `build.py` (`VO_LINES`) match what you said, then
`uv run --with pocketsphinx python docs/video/align_vo.py` and `node docs/video/render.js`, so the captions
and animations follow the new words.

---

## 4. What each 60-second demo shows

The voiceover lines land at fixed times, so **each beat must be on screen at its time.** Times in brackets
are seconds into the 60-second clip.

### Project Defense, 0:30–1:30

| Video time (clip time) | On screen | Sound |
|---|---|---|
| 0:30–0:42 (0–12 s) | Pick `bank-transfer` → Start → the audit (sped up) → the diagram, the flawed node turns red | VO `0030` |
| 0:42–0:52 (12–22 s) | The attack: 200 transfers stream live → the dollar loss, big | VO `0042` |
| 0:52–1:02 (22–32 s) | The grill: the interviewer asks why, you answer out loud | **the recording's own sound**, real speed |
| 1:02–1:18 (32–48 s) | Grading → your fix in the editor (sped up) → Verify → the line holds → **MERGE GATE: PASS** | VO `0102`, `0106` |
| 1:18–1:30 (48–60 s) | The report: before/after numbers, grill scores, how much of the fix was yours | VO `0118` |

### Live Coding Interview, 1:30–2:30

| Video time (clip time) | On screen | Sound |
|---|---|---|
| 1:30–1:38 (0–8 s) | Setup → the interviewer presents the problem | VO `0130` |
| 1:38–1:52 (8–22 s) | You state your approach out loud and start coding | **the recording's own sound** |
| 1:52–2:00 (22–30 s) | You skip the empty case → the interviewer's spoken nudge | **the recording's own sound** |
| 2:00–2:15 (30–45 s) | The fix (sped up) → paste a block, the neutral note → Run → Submit, hidden tests pass | VO `0200`, `0205` |
| 2:15–2:30 (45–60 s) | The report: the scores, then scrub the replay | VO `0215` |

---

## 5. Cutting a 3-minute take down to 60 seconds

Record each mode in **one full, real take** (about 3 minutes), then keep only the parts below. No video editor
needed: write a cut list and `build.py` does the cuts.

### Project Defense: keep, speed up, delete

| | What | Target length |
|---|---|---|
| ✅ Keep | Picking `bank-transfer` and pressing Start | 3 s |
| ⏩ Speed up 6–8× | The audit wait ("Muse Wonder is reading…") | ~5 s |
| ✅ Keep | The diagram appearing and the node turning red | 4 s |
| ✅ Keep (2× if long) | The attack streaming and the dollar loss | 10 s |
| ✅ Keep, real speed | **One** grill question and your spoken answer | 10 s |
| ⏩ Speed up 4× | Grading, then you fixing the code | ~8 s |
| ✅ Keep | Verify: the line holding flat, **MERGE GATE: PASS** | 8 s |
| ✅ Keep | The report: before/after, grill scores, fix share | 12 s |
| ❌ Delete | Page loads, the upload form, scrolling, a second finding or a follow-up question, waiting for grading, navigating to the report, anything that fails and is retried | — |

### Live Coding Interview: keep, speed up, delete

| | What | Target length |
|---|---|---|
| ✅ Keep | Setup screen → Start → the problem appearing | 8 s |
| ✅ Keep, real speed | You stating your approach out loud, the first lines of code | 14 s |
| ✅ Keep, real speed | Skipping the empty case and the interviewer's spoken nudge | 8 s |
| ⏩ Speed up 4× | Typing the fix | ~5 s |
| ✅ Keep | The paste and its neutral note | 3 s |
| ✅ Keep | Run, then Submit: hidden tests pass | 7 s |
| ✅ Keep | The report scores, then scrubbing the replay | 15 s |
| ❌ Delete | The warm-up chat, clarifying questions beyond the first, failed runs, long silences, the wrap-up complexity questions, waiting for the report | — |

### The cut list

Watch the take, note the times, and save them next to the recording as `clips/defense.cuts` (and
`clips/coding.cuts`): one span to keep per line, in order. Add a speed for a span to speed it up; sped-up spans
are muted and labelled "4x speed" on screen, so no cut is hidden.

```
# clips/defense.cuts: spans of the full take to keep (m:ss)
0:02 0:05          # pick bank-transfer, Start
0:05 0:45 8x       # the audit wait
0:45 0:49          # diagram, red node
0:52 1:02          # the attack and the dollar loss
1:20 1:30          # grill question + my answer
1:30 2:02 4x       # grading and the fix
2:05 2:13          # verify, merge gate PASS
2:30 2:42          # the report
```

`build.py` prints the length after cuts; aim for 60 s. A shorter clip holds its last frame; a longer one is
cut at 60 s.

### Recording tips

1. Run `make dev` (or the deployed site) on a laptop with the real `.env`. Warm up first: run one Defense
   audit on `bank-transfer` so it's cached.
2. Chrome full screen (F11), browser zoom **125%**, 1920×1080, notifications off.
3. Record with OBS (or QuickTime / Win+G) **with system audio on**, so the interviewer's voice is in the clip.
4. Real flows only: never MOCK mode or the scripted `/demo` rooms (PLAN §2). Don't show SAM "circle the flaw"
   (it's only in the scripted room).

---

## 6. Building the final video

You need **Python 3 and ffmpeg** (`brew install ffmpeg` / `winget install ffmpeg`).

```bash
git fetch origin claude/happy-shannon-oapm70 && git checkout claude/happy-shannon-oapm70
python3 docs/video/build.py        # → docs/video/out/ares-demo.mp4
```

| File | What it does |
|---|---|
| `clips/defense.mp4`, `clips/coding.mp4` (+ optional `.cuts`) | The demo recordings (mp4/mov/webm/mkv), scaled to 1920×1080 @ 30 fps, cut by the cut list, then fitted to 60 s. Each keeps its own sound |
| `vo_lines/<MMSS>.m4a` | The voiceover, one file per line (§3). Nothing is cut out: each gets one fixed gain (−16 LUFS) and is shifted so its first word lands on its start time; lines that run long are flagged |
| `vo_lines/timing.json` | When each word is spoken (from `align_vo.py`). Drives the captions and the animations |
| `music.mp3` | Background music (not committed; get the file from whoever has it on the team). −26 LUFS in the gaps, 8 dB lower under any voice, smooth ramps, faded in and out |
| `captions.srt` | Optional: replaces the generated captions |

### Submission checklist
- [ ] Under 3:00 (the timeline is 2:56), both demo slates replaced, no placeholder left.
- [ ] Line `0000` recorded and in place.
- [ ] Uploaded to YouTube as **unlisted**; the link opens in a private window. Allow time for the upload.
- [ ] Repo public, deployed URL works from a clean browser (PLAN §20.2).

---

## 7. Files here

| File | What it is |
|---|---|
| `README.md` | This guide |
| `ares-demo-preview.mp4` | The current preview cut |
| `scenes.html` | The problem, hook, technical loop, end card and slates (frame-accurate: `window.seek(scene, t)`) |
| `render.js` | Renders those into `build/` (following the word timings) and captures the landing page |
| `build.py` | Assembles `out/ares-demo.mp4` from `build/`, `clips/`, `vo_lines/` and `music.mp3` |
| `align_vo.py` | Finds when each voiceover word is spoken → `vo_lines/timing.json` |
| `build/`, `vo_lines/` | Rendered segments and the voiceover (committed) |
