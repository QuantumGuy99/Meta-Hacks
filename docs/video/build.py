"""Assemble the 2:58 demo video from rendered segments, your screen recordings and an optional voiceover.

Usage (from the repo root):  python3 docs/video/build.py
Needs: ffmpeg, and docs/video/build/ from `node docs/video/render.js`.

Recordings go in docs/video/clips/ (mp4, mov, webm or mkv), named after the slot:
  defense, defense_report, coding, coding_report
Each is scaled to 1920x1080 at 30 fps. Only its first N seconds are used (N = the slot length); a shorter
clip holds its last frame. A missing clip shows a placeholder slate with the slot's clock.
Each clip keeps its own sound (the interviewer's voice, your spoken answers).
Optional: docs/video/vo.(wav|m4a|mp3) is mixed over the whole video (leave gaps where the clip's sound matters); docs/video/captions.srt is burned in.
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
    srt = DIR / "captions.srt"
    final = OUT / "ares-demo.mp4"
    args = ["-i", str(joined)]
    if vo:
        args += ["-i", str(vo), "-filter_complex",
                 f"[0:a]volume={CLIP_VOLUME}[a0];[a0][1:a]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]",
                 "-map", "[a]"]
    else:
        args += ["-map", "0:a"]
    vf = []
    if srt.exists():
        style = "FontName=Inter,FontSize=20,PrimaryColour=&H00FFFFFF,BackColour=&H99000000,BorderStyle=4,Outline=0,MarginV=36"
        vf = ["-vf", f"subtitles={srt}:force_style='{style}'"]
    video = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"] if vf else ["-c:v", "copy"]
    ffmpeg(*args, "-map", "0:v", *vf, *video, "-c:a", "aac", "-b:a", "192k",
           "-t", str(start), "-movflags", "+faststart", str(final))
    shutil.rmtree(work)
    print(f"\n{final.relative_to(DIR.parent.parent)}  ({start // 60}:{start % 60:02d})"
          f"  voiceover: {vo.name if vo else 'none'}  captions: {'yes' if srt.exists() else 'no'}")


if __name__ == "__main__":
    main()
