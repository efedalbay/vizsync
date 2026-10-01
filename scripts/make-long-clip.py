"""Repeat a WAV clip until it is about MINUTES long, to measure recognition speed.

Usage: uv run python scripts/make-long-clip.py CLIP OUTPUT.wav [--minutes 13]

Recognition time depends on the length of the audio, not on what is said, so a clip repeated
many times is a fair stand-in for a long narration.
"""

import argparse
import math
import sys
import wave
from pathlib import Path


def repeat_clip(source: Path, target: Path, minutes: float) -> tuple[int, float]:
    """Write ``source`` repeated to ``target``; return (repeats, length in seconds)."""
    with wave.open(str(source), "rb") as reader:
        params = reader.getparams()
        frames = reader.readframes(reader.getnframes())
    seconds = params.nframes / params.framerate
    repeats = max(1, math.ceil(minutes * 60 / seconds))
    with wave.open(str(target), "wb") as writer:
        writer.setparams(params)
        for _ in range(repeats):
            writer.writeframes(frames)
    return repeats, repeats * seconds


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("clip", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--minutes", type=float, default=13.0)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    repeats, seconds = repeat_clip(args.clip, args.output, args.minutes)
    print(f"Wrote {args.output}: {repeats} repeats, {seconds / 60:.1f} minutes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
