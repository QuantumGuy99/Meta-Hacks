# Demo video (2:58)

The cut follows the agreed format: hook → who it's for → Project Defense → its report → Live Coding → its
report → technical → end card. Four segments are already made here (rendered or captured from the real app).
The four product segments are **slots for live screen recordings**: they show a placeholder slate with a
running clock until you drop a recording in. Never fill a slot with MOCK mode or the scripted `/demo` rooms
(PLAN §2: no mocked flows in the video).

| Time | Segment | Source |
|---|---|---|
| 0:00–0:20 | Hook | `scenes.html` (rendered) |
| 0:20–0:30 | Who it's for | the real landing page, captured |
| 0:30–1:30 | Project Defense | **`clips/defense.mp4`** (record it) |
| 1:30–1:40 | Defense report | **`clips/defense_report.mp4`** |
| 1:40–2:20 | Live Coding Interview | **`clips/coding.mp4`** |
| 2:20–2:32 | Coding report + replay | **`clips/coding_report.mp4`** |
| 2:32–2:52 | Technical (the closed loop) | `scenes.html` (rendered) |
| 2:52–2:58 | End card | `scenes.html` (rendered) |

## Build it

```bash
cd frontend && pnpm dev                      # only needed to re-capture the landing page
node docs/video/render.js --live https://your-app.vercel.app   # optional: puts the live URL on the end card
python3 docs/video/build.py                  # → docs/video/out/ares-demo.mp4
```

`build.py` scales every recording to 1920×1080 at 30 fps, uses only its first N seconds (N = slot length) and
holds the last frame if it's shorter. Each recording **keeps its own sound** (the interviewer's voice, your
spoken answers). A voiceover at `docs/video/vo.wav` (or `.m4a`/`.mp3`) is mixed over the whole video, and
`docs/video/captions.srt`, if present, is burned in (recommended: the finals are watched live in a room).

## Recording the four slots (on a machine with the real `.env`)

1. `make dev` (or the deployed site), Chrome full screen (F11), browser zoom 125%, 1920×1080.
2. Record with OBS (or QuickTime / Win+G) **with system audio**, so the interviewer's voice is in the clip.
3. Warm up first: open the site once, run one Defense audit on `bank-transfer` so the audit is cached.
4. Trim each take to its slot, e.g. `ffmpeg -ss 00:01:05 -to 00:02:05 -i raw.mov docs/video/clips/defense.mp4`.
5. Real speed only. If you cut a wait (the audit), show a label such as "audit: 44 s, shortened".

What each slot must show (the slates list the same beats with times):

- **defense (60 s):** pick `bank-transfer` → Muse Wonder audit → diagram, flawed node red → Muse Spark writes
  the attack → 200 concurrent transfers stream → the real dollar loss → the voice grill (question, answer,
  follow-up) → fix in the editor → Verify re-runs the attack, the line holds → **MERGE GATE: PASS**.
- **defense_report (10 s):** before/after numbers, grill scores, how much of the fix was yours.
- **coding (40 s):** setup (active, voice on) → state the approach out loud → code → skip the empty-input
  case → the spoken nudge → paste a block, the neutral note → Run, Submit, hidden tests pass.
- **coding_report (12 s):** the scores, then scrub the replay (code writes itself, synced with the transcript).

Don't show SAM "circle the flaw": it only exists in the scripted demo room, not the live rooms.

## Voiceover script (~2.5 words per second)

Leave the VO silent where the clip's own sound carries the moment (the interviewer's questions, your answers).

| Time | Voiceover |
|---|---|
| 0:00 | AI writes code faster than we can understand it. An agent builds this transfer API in seconds, and it passes the happy path. But could you explain why it loses money under load? |
| 0:15 | Ares, built on Meta's Muse models, proves you understand your code. |
| 0:20 | We're students. We prep for interviews and ship with AI agents every day. Ares is an AI interviewer that grades how you engineer, not just your answer. |
| 0:30 | In Project Defense, you bring code, even code your AI wrote. Muse Wonder reads the whole project in one pass and finds the riskiest flaw. |
| 0:48 | Muse Spark writes a targeted attack, and Ares fires two hundred concurrent transfers at the real app in a sandbox. *[the real number]* just disappeared. |
| 1:00 | *(VO silent: the interviewer's voice question and your spoken answer.)* Muse Voice Transcribe hears the answer, and two Meta models grade it. A point counts only if both agree. |
| 1:14 | I fix it myself. Ares re-runs the exact same attack. It holds. Merge gate: pass. |
| 1:30 | The report shows the before and after, my grill scores, and how much of the fix was mine. |
| 1:40 | The Live Coding Interview works the same way. I state my approach out loud, and Muse Spark follows every edit. |
| 1:58 | *(VO silent: the spoken nudge.)* It noticed the missing empty-input case, without handing me the answer. |
| 2:08 | A paste gets a neutral note. Submit runs the hidden tests in the sandbox. |
| 2:20 | Muse Wonder writes the report: scores for how I solved it, and a replay of my code, synced with everything I said. |
| 2:32 | Under the hood, it's one closed loop with a Meta model at every step. The model suggests, code decides: scores and verdicts are computed in Python, and a leak guard checks every line, so the interviewer never hands over the answer. |
| 2:52 | Ares. Prove you understand your code. |

## Files

- `scenes.html`: the hook, the technical loop, the end card and the slates (frame-accurate, `window.seek(scene, t)`).
- `render.js`: renders those to `build/` and captures the landing page with a "who it's for" banner.
- `build.py`: assembles `out/ares-demo.mp4`. `build/`, `out/`, `clips/` and voiceover files are gitignored.
