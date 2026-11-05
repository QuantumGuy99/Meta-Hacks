"""Find when each word of each voiceover line is spoken, for captions and animation timing.

Run after adding or re-recording a line in docs/video/vo_lines/:
    uv run --with pocketsphinx python docs/video/align_vo.py
Writes docs/video/vo_lines/timing.json (committed). build.py and render.js read it; without it they fall back to
silence detection and evenly spread captions.

It aligns the recording against the line's script text in build.py (VO_LINES), so the text there must match
what was actually said. A line that doesn't align is reported; fix its text in VO_LINES and run again.
"""

import importlib.util
import json
import re
import subprocess
from pathlib import Path

from pocketsphinx import Decoder

DIR = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("build", DIR / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

EXTRA = {"meta's": "M EH T AH Z", "meta": "M EH T AH", "synced": "S IH NG K T", "ares": "EH R IY Z"}


def norm(token: str) -> list[str]:
    return re.sub(r"[^a-z' ]", " ", token.lower().replace("-", " ")).split()


def pcm(path: Path) -> bytes:
    return subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-ar", "16000", "-ac", "1", "-f", "s16le", "-"],
                          capture_output=True, check=True).stdout


def align(dec: Decoder, path: Path, text: str) -> list[list] | None:
    tokens = text.split()
    sub = [(i, w) for i, tok in enumerate(tokens) for w in norm(tok)]
    known = [(i, w) for i, w in sub if dec.lookup_word(w)]
    dec.set_align_text(" ".join(w for _, w in known))
    dec.start_utt()
    dec.process_raw(pcm(path), full_utt=True)
    dec.end_utt()
    if dec.hyp() is None:
        return None
    segs = [(re.sub(r"\(\d+\)$", "", s.word), s.start_frame / 100, (s.end_frame + 1) / 100) for s in dec.seg()
            if s.word not in ("<sil>", "<s>", "</s>", "(NULL)")]
    if len(segs) != len(known):
        return None
    times: dict[int, list[float]] = {}
    for (i, _), (_, a, b) in zip(known, segs):
        t = times.setdefault(i, [a, b])
        t[0], t[1] = min(t[0], a), max(t[1], b)
    out = []
    for i, tok in enumerate(tokens):
        if i in times:
            out.append([tok, round(times[i][0], 2), round(times[i][1], 2)])
        else:  # a word the dictionary doesn't know: place it between its neighbours
            prev = out[-1][2] if out else 0.0
            nxt = next((times[j][0] for j in range(i + 1, len(tokens)) if j in times), prev + 0.3)
            out.append([tok, round(prev, 2), round(nxt, 2)])
    return out


def main() -> None:
    dec = Decoder(samprate=16000, bestpath=False)
    for word, phones in EXTRA.items():
        if not dec.lookup_word(word):
            dec.add_word(word, phones, True)
    timing = {}
    for name, at, _until, _cap, text in build.VO_LINES:
        src = build.find(name, build.VO_DIR, build.AUDIO_EXT)
        if not src:
            continue
        try:
            words = align(dec, src, text)
        except RuntimeError:
            words = None
        if not words:
            print(f"{name}: did NOT align. Make its text in build.py VO_LINES match the recording, then rerun.")
            continue
        timing[name] = {"at": at, "onset": words[0][1], "end": words[-1][2], "words": words}
        print(f"{name}: speech {words[0][1]:.2f}-{words[-1][2]:.2f} s, {len(words)} words")
    (build.VO_DIR / "timing.json").write_text(json.dumps(timing, indent=1) + "\n")


if __name__ == "__main__":
    main()
