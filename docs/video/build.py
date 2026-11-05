"""Assemble the 2:58 demo video from rendered segments, screen recordings, the voiceover and background music.

Usage (from the repo root):  python3 docs/video/build.py        Needs: Python 3 and ffmpeg.

Recordings go in docs/video/clips/ (mp4, mov, webm or mkv), named after the slot: defense, coding.
A long take can be cut down with clips/<slot>.cuts: one span to keep per line, `1:05 1:20`, or `1:20 1:50 4x`
to speed a span up (muted and labelled "4x speed").
Each is scaled to 1920x1080 at 30 fps. Only its first N seconds are used (N = the slot length); a shorter
clip holds its last frame. A missing clip shows a placeholder slate with the slot's clock.
Each clip keeps its own sound (the interviewer's voice, your spoken answers).

Voiceover: docs/video/vo_lines/<MMSS>.(m4a|wav|mp3), one file per script line (README §4). Nothing is cut out
of a recording: each is levelled with one fixed gain and shifted so its first word lands on the line's start
time. vo_lines/timing.json (from align_vo.py) gives the word timings for that and for the captions; without
it, silence detection finds the first word and captions are spread evenly.
Music: docs/video/music.(mp3|m4a|wav), not committed (licence). Levelled, then lowered under every voice
(the voiceover and the clips' own sound) and raised in the gaps, with smooth ramps.
docs/video/captions.srt, if present, replaces the generated captions.
Output: docs/video/out/ares-demo.mp4
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
BUILD, CLIPS, OUT = DIR / "build", DIR / "clips", DIR / "out"
FONT = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv")
AUDIO_EXT = (".m4a", ".wav", ".mp3", ".aac", ".ogg")
VO_DIR = DIR / "vo_lines"

# (slot, seconds, rendered source or None for a recording slot)
TIMELINE = [
    ("problem", 10, "00_problem.mp4"),
    ("hook", 13.5, "01_hook.mp4"),
    ("whofor", 6.5, "02_whofor.mp4"),
    ("defense", 60, None),
    ("coding", 60, None),
    ("tech", 14.5, "08_tech.mp4"),
    ("impact", 9.5, "08b_impact.mp4"),
    ("end", 5, "09_end.mp4"),
]

# (file, first word lands at s, must end by s, caption it?, what was said). Keep in sync with README §4.
# Files are named by their start time in the video.
VO_LINES = [
    ("0000", 0.4, 10.0, True, "Coding practice sites only check if your answer passes. But real interviewers grade how you think: your approach, your edge cases, how you explain it."),
    ("0010", 10.3, 19.8, False, "AI writes code faster than we can understand it. An agent builds this transfer API in seconds, and it passes the happy path. But could you explain why it loses money under load?"),
    ("0019", 19.9, 23.4, False, "Ares, built on Meta's Muse models, proves you understand your code."),
    ("0023", 23.6, 30.0, True, "We're students who prep for interviews and ship with AI agents every day. Ares grades how you engineer, not just your answer."),
    ("0030", 30.3, 42.0, True, "In Project Defense, you bring code, even code your AI wrote. Muse Wonder reads the whole project in one pass, maps it, and flags the riskiest flaw: a race condition in money transfers."),
    ("0042", 42.3, 52.0, True, "Muse Spark writes a targeted attack, and Ares fires two hundred concurrent transfers at the real app in a sandbox."),
    ("0102", 62.2, 66.3, True, "Muse Voice Transcribe hears me, and two Meta models grade it."),
    ("0106", 66.4, 78.0, True, "A point counts only if both agree. Then I fix it myself. Ares re-runs the exact same attack. It holds. Merge gate: pass."),
    ("0118", 78.3, 90.0, True, "The report shows the before and after, my grill scores, and how much of the fix was mine."),
    ("0130", 90.3, 98.0, True, "The Live Coding Interview works the same way. I explain my approach out loud, and Muse Spark follows every edit."),
    ("0200", 120.2, 125.0, True, "It caught the missing empty case, without giving me the answer."),
    ("0205", 125.2, 135.0, True, "A paste gets a neutral note, not an accusation. Submit runs the hidden tests in the sandbox. All pass."),
    ("0215", 135.3, 150.0, True, "Muse Wonder writes the report: scores for how I solved it, and a replay of my code, synced with everything I said."),
    ("0230", 150.2, 164.5, False, "Under the hood, it's one closed loop with a Meta model at every step. The model suggests, code decides: scores and verdicts are computed in Python, and a leak guard checks every line, so the interviewer never hands over the answer."),
    ("0244", 164.8, 173.8, True, "AI wrote the code. Meta's models break it and grade you. Next: hiring teams and universities grading real understanding, not memorized answers."),
    ("0254", 174.4, 179.0, False, "Ares. Prove you understand your code."),
]

NORM = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,fps=30,format=yuv420p,setsar=1"
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
SILENCE = ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
CLIP_VOLUME = 1.0       # the recordings' own sound under the voiceover
VOICE_LUFS = -16.0      # every voiceover line is brought to this loudness
MUSIC_GAP_LUFS = -26.0  # music where nobody speaks (10 dB under the voice)
MUSIC_DUCK_DB = -8.0    # extra drop under speech (music then sits ~18 dB under the voice)
DUCK_IN, DUCK_OUT = 0.3, 0.8  # seconds to dip before speech, and to come back after it


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


def loudness(path: Path) -> float:
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", err)[-1])


def voiced(path: Path, offset: float = 0.0, noise: str = "-40dB") -> list[tuple[float, float]]:
    """Spans with sound in a file, shifted by offset."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", f"silencedetect=noise={noise}:d=0.4",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    total = duration(path)
    spans, cur = [], 0.0
    for s, e in zip(starts, ends + [total] * (len(starts) - len(ends))):
        if s > cur + 0.05:
            spans.append((offset + cur, offset + max(s, 0)))
        cur = e
    if cur < total - 0.05 and len(starts) <= len(ends):
        spans.append((offset + cur, offset + total))
    return spans


def srt_time(t: float) -> str:
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def caption_cues(words: list[tuple[str, float, float]], width: int = 56) -> list[tuple[float, float, str]]:
    """Groups timed words into one-line captions, breaking at sentence ends, pauses and the width."""
    cues, cur = [], []
    for i, (w, a, b) in enumerate(words):
        cur.append((w, a, b))
        text = " ".join(x[0] for x in cur)
        nxt = words[i + 1] if i + 1 < len(words) else None
        long_next = nxt and len(text) + 1 + len(nxt[0]) > width
        pause = nxt and nxt[1] - b > 0.35 and len(text) > 18
        stop = w.endswith((".", "?", "!", ":")) and len(text) > 18
        if not nxt or long_next or pause or stop:
            cues.append([cur[0][1], cur[-1][2], text])
            cur = []
    for i, c in enumerate(cues):  # linger a little, never into the next caption
        c[1] = min(c[1] + 0.3, cues[i + 1][0] - 0.02) if i + 1 < len(cues) else c[1] + 0.4
    return [tuple(c) for c in cues]


def build_voiceover(work: Path, total: int) -> tuple[Path | None, list, list, list[str]]:
    """Returns (track, caption cues, speech spans, report)."""
    timing = json.loads((VO_DIR / "timing.json").read_text()) if (VO_DIR / "timing.json").exists() else {}
    placed, cues, spans, report = [], [], [], []
    for name, at, until, caption, text in VO_LINES:
        src = find(name, VO_DIR, AUDIO_EXT)
        if not src:
            report.append(f"  {name}  missing")
            continue
        t = timing.get(name)
        if t:
            onset, end = t["onset"], t["end"]
            words = [(w, at + a - onset, at + b - onset) for w, a, b in t["words"]]
        else:
            v = voiced(src, noise="-50dB")
            onset, end = (v[0][0], v[-1][1]) if v else (0.0, duration(src))
            toks = text.split()
            step = (end - onset) / max(1, len(toks))
            words = [(w, at + i * step, at + (i + 1) * step) for i, w in enumerate(toks)]
        gain = VOICE_LUFS - loudness(src)
        clean = work / f"vo_{name}.wav"
        ffmpeg("-i", str(src), "-af", f"highpass=f=70,volume={gain:.2f}dB,alimiter=limit=0.89:level=0,"
               "aresample=48000,aformat=channel_layouts=stereo", str(clean))
        delay = at - onset
        speech, limit = end - onset, until - at
        note = f"{speech:4.1f}s of {limit:4.1f}s"
        if speech > limit:
            note += f"  TOO LONG by {speech - limit:.1f}s: re-record or shorten"
        report.append(f"  {name}  {note}" + ("" if t else "  (no word timing: run align_vo.py)"))
        placed.append((clean, delay))
        spans.append((at, at + speech))
        if caption:
            cues += caption_cues(words)
    if not placed:
        return None, [], [], report
    track = work / "vo_track.wav"
    inputs = [arg for clean, _ in placed for arg in ("-i", str(clean))]
    pre = ""
    for i, (_, d) in enumerate(placed):
        pre += (f"[{i}:a]adelay={round(d * 1000)}:all=1[d{i}];" if d >= 0
                else f"[{i}:a]atrim=start={-d:.3f},asetpts=PTS-STARTPTS[d{i}];")
    mix = "".join(f"[d{i}]" for i in range(len(placed)))
    ffmpeg(*inputs, "-filter_complex",
           f"{pre}{mix}amix=inputs={len(placed)}:normalize=0:dropout_transition=0,apad=whole_dur={total}[a]",
           "-map", "[a]", "-t", str(total), str(track))
    return track, cues, spans, report


def merge(spans: list[tuple[float, float]], gap: float = 1.2) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for a, b in sorted(spans):
        if out and a - out[-1][1] < gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def build_music(src: Path, work: Path, total: int, speech: list[tuple[float, float]]) -> Path:
    """Music levelled to MUSIC_GAP_LUFS, dipped by MUSIC_DUCK_DB under speech, faded in and out."""
    level = work / "music_level.wav"
    ffmpeg("-i", str(src), "-af", "dynaudnorm=f=1000:g=31:m=3:p=0.9,aresample=48000,aformat=channel_layouts=stereo",
           "-t", str(total), str(level))
    gain = MUSIC_GAP_LUFS - loudness(level)
    # duck(t) is 1 inside speech and ramps 0 -> 1 over DUCK_IN before it and 1 -> 0 over DUCK_OUT after it.
    terms = [f"clip(min((t-{a - DUCK_IN:.2f})/{DUCK_IN},({b + DUCK_OUT:.2f}-t)/{DUCK_OUT}),0,1)" for a, b in speech]
    duck = "0"
    for term in terms:
        duck = f"max({duck},{term})"
    end = min(total, duration(src))
    out = work / "music_track.wav"
    ffmpeg("-i", str(level), "-af",
           f"volume={gain:.2f}dB,volume='pow(10,({MUSIC_DUCK_DB}*{duck})/20)':eval=frame,"
           f"afade=t=in:d=1.5,afade=t=out:st={end - 4:.2f}:d=4,apad=whole_dur={total}",
           "-t", str(total), str(out))
    return out


def parse_t(x: str) -> float:
    m, _, sec = x.rpartition(":")
    return (int(m) * 60 if m else 0) + float(sec)


def apply_cuts(clip: Path, cuts: Path, work: Path) -> Path:
    """Keeps only the listed spans of a long take. Each line: `start end` or `start end 4x` (m:ss or seconds).
    A sped-up span is muted and labelled with its speed, so the cut is never hidden."""
    pieces = []
    for n, line in enumerate(l.split("#")[0].strip() for l in cuts.read_text().splitlines()):
        if not line:
            continue
        fields = line.replace("-", " ").split()
        a, b = parse_t(fields[0]), parse_t(fields[1])
        speed = float(fields[2].rstrip("x")) if len(fields) > 2 else 1.0
        piece = work / f"{clip.stem}_cut{n:02d}.mp4"
        vf = NORM
        if speed != 1.0:
            vf += (f",setpts=PTS/{speed},drawtext=fontfile={FONT}:fontsize=34:fontcolor=white:box=1:boxcolor=0x000000AA:"
                   f"boxborderw=14:x=w-tw-40:y=40:text='{speed:g}x speed'")
        if speed == 1.0 and has_audio(clip):
            audio = ["-map", "0:a:0", "-af", "aresample=48000"]
            inputs: list[str] = []
        else:
            audio, inputs = ["-map", "1:a", "-shortest"], SILENCE
        ffmpeg("-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(clip), *inputs, "-map", "0:v:0", *audio,
               "-vf", vf, *ENC, str(piece))
        pieces.append(piece)
    listing = work / f"{clip.stem}_cuts.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in pieces))
    out = work / f"{clip.stem}_edited.mp4"
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(listing), *ENC, str(out))
    return out


def clock(start: int) -> str:
    # drawtext expression: the video's overall timecode, for timing the voiceover against the slate.
    return f"video %{{eif\\:floor((t+{start})/60)\\:d}}\\:%{{eif\\:mod(floor(t+{start})\\,60)\\:d\\:2}}"


def main() -> None:
    if not BUILD.exists():
        sys.exit("docs/video/build/ is missing. Run: node docs/video/render.js")
    OUT.mkdir(exist_ok=True)
    work = OUT / "parts"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    parts, clip_speech, start = [], [], 0
    for slot, secs, rendered in TIMELINE:
        part = work / f"{len(parts):02d}_{slot}.mp4"
        if rendered:
            ffmpeg("-i", str(BUILD / rendered), *SILENCE, "-map", "0:v", "-map", "1:a", "-vf", NORM,
                   "-t", str(secs), *ENC, str(part))
            note = "rendered"
        elif clip := find(slot, CLIPS, VIDEO_EXT):
            if (CLIPS / f"{slot}.cuts").exists():
                clip = apply_cuts(clip, CLIPS / f"{slot}.cuts", work)
            if has_audio(clip):
                inputs, audio = [], ["-map", "0:a:0", "-af", "aresample=48000,apad"]
            else:
                inputs, audio = SILENCE, ["-map", "1:a"]
            ffmpeg("-i", str(clip), *inputs, "-map", "0:v:0", *audio,
                   "-vf", f"{NORM},tpad=stop_mode=clone:stop_duration={secs}", "-t", str(secs), *ENC, str(part))
            clip_speech += voiced(part, offset=start)
            note = f"clip {clip.name}" + (f"  ({duration(clip):.0f}s after cuts)" if "_edited" in clip.name else "")
        else:
            slate = BUILD / f"slate_{slot}.jpg"
            dt = (f"drawtext=fontfile={FONT}:fontsize=40:fontcolor=0xffb340:x=w-tw-200:y=150:"
                  f"text='{clock(start)}'")
            ffmpeg("-loop", "1", "-framerate", "30", "-i", str(slate), *SILENCE, "-map", "0:v", "-map", "1:a",
                   "-vf", f"{NORM},{dt}", "-t", str(secs), *ENC, str(part))
            note = "PLACEHOLDER slate"
        print(f"{int(start) // 60}:{start % 60:04.1f}  {slot:<15} {secs:>4}s  {note}")
        parts.append(part)
        start += secs

    listing = work / "list.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts))
    joined = work / "joined.mp4"
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(joined))

    vo, cues, vo_speech, report = build_voiceover(work, start) if VO_DIR.exists() else (None, [], [], [])
    music_src = find("music", DIR, AUDIO_EXT)
    music = build_music(music_src, work, start, merge(vo_speech + clip_speech)) if music_src else None

    srt = DIR / "captions.srt" if (DIR / "captions.srt").exists() else None
    if not srt and cues:
        srt = work / "captions.srt"
        srt.write_text("".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{txt}\n\n" for i, (a, b, txt) in enumerate(cues, 1)))

    final = OUT / "ares-demo.mp4"
    args = ["-i", str(joined)]
    extra = [p for p in (vo, music) if p]
    for p in extra:
        args += ["-i", str(p)]
    mix = f"[0:a]volume={CLIP_VOLUME}[a0];[a0]" + "".join(f"[{i + 1}:a]" for i in range(len(extra)))
    args += ["-filter_complex", f"{mix}amix=inputs={1 + len(extra)}:duration=first:dropout_transition=0:normalize=0,"
             "alimiter=limit=0.95:level=0[a]", "-map", "[a]"]
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
    print(f"\n{final.relative_to(DIR.parent.parent)}  ({int(start) // 60}:{int(start) % 60:02d})"
          f"  voiceover: {'yes' if vo else 'none'}  music: {music_src.name if music_src else 'none'}"
          f"  captions: {'yes' if srt else 'no'}")


if __name__ == "__main__":
    main()
