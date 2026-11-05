"""Assemble the 2:58 demo video from rendered segments, your screen recordings and an optional voiceover.

Usage (from the repo root):  python3 docs/video/build.py
Needs: ffmpeg, and docs/video/build/ from `node docs/video/render.js`.

Recordings go in docs/video/clips/ (mp4, mov, webm or mkv), named after the slot:
  defense, defense_report, coding, coding_report
Each is scaled to 1920x1080 at 30 fps. Only its first N seconds are used (N = the slot length); a shorter
clip holds its last frame. A missing clip shows a placeholder slate with the slot's clock.
Each clip keeps its own sound (the interviewer's voice, your spoken answers).
Voiceover, either way:
  - docs/video/vo_lines/<MMSS>.(m4a|wav|mp3), one file per script line (README §4). Each is trimmed of silence,
    levelled, placed at its start time and checked against its time limit (up to 10% too long is sped up).
    Captions are made from the script; a vo_lines/<MMSS>.txt overrides a line's caption text.
  - or docs/video/vo.(wav|m4a|mp3), one track mixed from 0:00.
docs/video/captions.srt, if present, replaces the generated captions.
Output: docs/video/out/ares-demo.mp4
"""

import shutil
import subprocess
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
BUILD, CLIPS, OUT = DIR / "build", DIR / "clips", DIR / "out"
FONT = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv")

# (slot, seconds, rendered source or None for a recording slot)
TIMELINE = [
    ("hook", 20, "01_hook.mp4"),
    ("whofor", 10, "02_whofor.mp4"),
    ("defense", 60, None),
    ("defense_report", 10, None),
    ("coding", 40, None),
    ("coding_report", 12, None),
    ("tech", 20, "08_tech.mp4"),
    ("end", 6, "09_end.mp4"),
]
NORM = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,fps=30,format=yuv420p,setsar=1"
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
SILENCE = ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
CLIP_VOLUME = 1.0  # the recordings' own sound (interviewer voice, your answers) under the voiceover
VO_DIR = DIR / "vo_lines"
AUDIO_EXT = (".m4a", ".wav", ".mp3", ".aac", ".ogg")

# (file, speech starts at s, must end by s, caption it?, script text). Keep in sync with README §4.
VO_LINES = [
    ("0000", 0.8, 15, False, "AI writes code faster than we can understand it. An agent builds this transfer API in seconds, and it passes the happy path. But could you explain why it loses money under load?"),
    ("0015", 15.2, 20, False, "Ares, built on Meta's Muse models, proves you understand your code."),
    ("0020", 20.2, 30, True, "We're students who prep for interviews and ship with AI agents every day. Ares grades how you engineer, not just your answer."),
    ("0030", 30.2, 48, True, "In Project Defense, you bring code, even code your AI wrote. Muse Wonder reads the whole project in one pass, maps it, and flags the riskiest flaw: a race condition in money transfers."),
    ("0048", 48.2, 60, True, "Muse Spark writes a targeted attack, and Ares fires two hundred concurrent transfers at the real app in a sandbox. Thousands of dollars just disappeared."),
    ("0109", 69.2, 74, True, "Muse Voice Transcribe hears me, and two Meta models grade it."),
    ("0114", 74.2, 90, True, "A point counts only if both agree. Then I fix it myself. Ares re-runs the exact same attack. It holds. Merge gate: pass."),
    ("0130", 90.2, 100, True, "The report shows the before and after, my grill scores, and how much of the fix was mine."),
    ("0140", 100.2, 108, True, "The Live Coding Interview works the same way. I explain my approach out loud, and Muse Spark follows every edit."),
    ("0203", 123.2, 128, True, "It caught the missing empty case, without giving me the answer."),
    ("0208", 128.2, 140, True, "A paste gets a neutral note, not an accusation. Submit runs the hidden tests in the sandbox. All pass."),
    ("0220", 140.2, 152, True, "Muse Wonder writes the report: scores for how I solved it, and a replay of my code, synced with everything I said."),
    ("0232", 152.2, 172, True, "Under the hood, it's one closed loop with a Meta model at every step. The model suggests, code decides: scores and verdicts are computed in Python, and a leak guard checks every line, so the interviewer never hands over the answer."),
    ("0252", 172.4, 178, False, "Ares. Prove you understand your code."),
]
VO_CLEAN = ("highpass=f=80,"
            "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,"
            "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.15,areverse,"
            "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,aformat=channel_layouts=stereo")


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def find(stem: str, folder: Path, exts: tuple[str, ...]) -> Path | None:
    for ext in exts:
        p = folder / (stem + ext)
        if p.exists():
            return p
    return None


def has_audio(path: Path) -> bool:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return bool(out.strip())


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout
    return float(out.strip())


def srt_time(t: float) -> str:
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def chunks(text: str, width: int = 64) -> list[str]:
    out, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > width:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
        if cur.endswith((".", "?", ":")) and len(cur) > width * 0.45:
            out.append(cur)
            cur = ""
    return out + ([cur] if cur else [])


def build_voiceover(work: Path, total: int) -> tuple[Path | None, Path | None, list[str]]:
    """Places each vo_lines/<MMSS> file at its start time. Returns (track, captions, report lines)."""
    placed, report, cues = [], [], []
    for name, at, until, caption, text in VO_LINES:
        src = find(name, VO_DIR, AUDIO_EXT)
        if not src:
            report.append(f"  {name}  missing")
            continue
        clean = work / f"vo_{name}.wav"
        ffmpeg("-i", str(src), "-af", VO_CLEAN, str(clean))
        dur, limit = duration(clean), until - at
        note = f"{dur:4.1f}s of {limit:4.1f}s"
        if dur > limit:
            ratio = dur / limit
            if ratio <= 1.10:
                sped = work / f"vo_{name}_fit.wav"
                ffmpeg("-i", str(clean), "-af", f"atempo={ratio:.4f}", str(sped))
                clean, dur = sped, duration(sped)
                note += f"  sped up {ratio:.2f}x to fit"
            else:
                note += f"  TOO LONG by {dur - limit:.1f}s: re-record or shorten (it runs into the next part)"
        report.append(f"  {name}  {note}")
        placed.append((clean, at))
        if caption:
            words = (VO_DIR / f"{name}.txt").read_text().strip() if (VO_DIR / f"{name}.txt").exists() else text
            parts = chunks(words)
            weights = [len(p) for p in parts]
            t = at
            for part, w in zip(parts, weights):
                span = dur * w / sum(weights)
                cues.append((t, t + span, part))
                t += span
    if not placed:
        return None, None, report
    track = work / "vo_track.wav"
    inputs = [arg for clean, _ in placed for arg in ("-i", str(clean))]
    delays = "".join(f"[{i}:a]adelay={round(at * 1000)}:all=1[d{i}];" for i, (_, at) in enumerate(placed))
    mix = "".join(f"[d{i}]" for i in range(len(placed)))
    ffmpeg(*inputs, "-filter_complex",
           f"{delays}{mix}amix=inputs={len(placed)}:normalize=0:dropout_transition=0,apad=whole_dur={total}[a]",
           "-map", "[a]", "-t", str(total), str(track))
    srt = None
    if cues:
        srt = work / "captions.srt"
        srt.write_text("".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{txt}\n\n"
                               for i, (a, b, txt) in enumerate(cues, 1)))
    return track, srt, report


def clock(start: int) -> str:
    # drawtext expression: the video's overall timecode, for timing the voiceover against the slate.
    return (f"video %{{eif\\:floor((t+{start})/60)\\:d}}\\:%{{eif\\:mod(floor(t+{start})\\,60)\\:d\\:2}}")


def main() -> None:
    if not BUILD.exists():
        sys.exit("docs/video/build/ is missing. Run: node docs/video/render.js")
    OUT.mkdir(exist_ok=True)
    work = OUT / "parts"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    parts, start = [], 0
    for slot, secs, rendered in TIMELINE:
        part = work / f"{len(parts):02d}_{slot}.mp4"
        if rendered:
            ffmpeg("-i", str(BUILD / rendered), *SILENCE, "-map", "0:v", "-map", "1:a", "-vf", NORM,
                   "-t", str(secs), *ENC, str(part))
            note = "rendered"
        elif clip := find(slot, CLIPS, VIDEO_EXT):
            if has_audio(clip):
                inputs, audio = [], ["-map", "0:a:0", "-af", "aresample=48000,apad"]
            else:
                inputs, audio = SILENCE, ["-map", "1:a"]
            ffmpeg("-i", str(clip), *inputs, "-map", "0:v:0", *audio,
                   "-vf", f"{NORM},tpad=stop_mode=clone:stop_duration={secs}", "-t", str(secs), *ENC, str(part))
            note = f"clip {clip.name}"
        else:
            slate = BUILD / f"slate_{slot}.jpg"
            dt = (f"drawtext=fontfile={FONT}:fontsize=40:fontcolor=0xffb340:x=w-tw-200:y=150:"
                  f"text='{clock(start)}'")
            ffmpeg("-loop", "1", "-framerate", "30", "-i", str(slate), *SILENCE, "-map", "0:v", "-map", "1:a",
                   "-vf", f"{NORM},{dt}", "-t", str(secs), *ENC, str(part))
            note = "PLACEHOLDER slate"
        print(f"{start // 60}:{start % 60:02d}  {slot:<15} {secs:>3}s  {note}")
        parts.append(part)
        start += secs

    listing = work / "list.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts))
    joined = work / "joined.mp4"
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(joined))

    vo = find("vo", DIR, (".wav", ".m4a", ".mp3"))
    srt = DIR / "captions.srt" if (DIR / "captions.srt").exists() else None
    report: list[str] = []
    if not vo and VO_DIR.exists():
        vo, made_srt, report = build_voiceover(work, start)
        srt = srt or made_srt
    final = OUT / "ares-demo.mp4"
    args = ["-i", str(joined)]
    if vo:
        args += ["-i", str(vo), "-filter_complex",
                 f"[0:a]volume={CLIP_VOLUME}[a0];[a0][1:a]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]",
                 "-map", "[a]"]
    else:
        args += ["-map", "0:a"]
    vf = []
    if srt:
        style = ("FontName=Inter,FontSize=13,Bold=1,PrimaryColour=&H00FFFFFF,BackColour=&H99000000,"
                 "BorderStyle=4,Outline=6,Shadow=0,MarginV=22")
        vf = ["-vf", f"subtitles={srt}:force_style='{style}'"]
    video = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"] if vf else ["-c:v", "copy"]
    ffmpeg(*args, "-map", "0:v", *vf, *video, "-c:a", "aac", "-b:a", "192k",
           "-t", str(start), "-movflags", "+faststart", str(final))
    if report:
        print("\nvoiceover lines:\n" + "\n".join(report))
    shutil.rmtree(work)
    print(f"\n{final.relative_to(DIR.parent.parent)}  ({start // 60}:{start % 60:02d})"
          f"  voiceover: {vo.name if vo else 'none'}  captions: {'yes' if srt else 'no'}")


if __name__ == "__main__":
    main()
