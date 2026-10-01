"""Compare how the voice-activity settings move the paragraph times, against the sound itself.

Usage: uv run python scripts/diagnose-times.py [CLIP] [--script SCRIPT] [--model base.en]

The reference is the sound: the moments where the signal rises above and falls below silence,
which for a clip with clear pauses between paragraphs are the real start and end of each
paragraph. For each voice-activity setting the clip is aligned whole and cut into three parts
(like the slow tests), and every paragraph time is printed as its difference to the reference
(+ means later than the sound). Needs a PCM WAV with the pauses described in
tests/fixtures/README.md.
"""

import argparse
import array
import math
import sys
import wave
from pathlib import Path

from vizsync.asr.faster_whisper import FasterWhisperTranscriber
from vizsync.audio.inputs import AudioMode, plan_audio
from vizsync.pipeline import AlignmentResult, run_alignment
from vizsync.script.models import Script, TextMode
from vizsync.script.parser import load_script

ROOT = Path(__file__).resolve().parents[1]
FRAME_SECONDS = 0.01
SETTINGS: list[tuple[str, bool, dict[str, int] | None]] = [
    ("library default (pad 400, silence 2000)", True, {"speech_pad_ms": 400}),
    ("pad 200, silence 2000", True, {"speech_pad_ms": 200}),
    ("pad 100, silence 2000 (vizsync default)", True, {"speech_pad_ms": 100}),
    ("pad 100, silence 500", True, {"speech_pad_ms": 100, "min_silence_duration_ms": 500}),
    ("pad 50, silence 300", True, {"speech_pad_ms": 50, "min_silence_duration_ms": 300}),
    ("pad 0, silence 300", True, {"speech_pad_ms": 0, "min_silence_duration_ms": 300}),
    ("no voice activity filter", False, None),
]


def read_wav(path: Path) -> tuple[int, list[int]]:
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() != 2:
            raise SystemExit("The clip must be a 16-bit PCM WAV.")
        channels = wav.getnchannels()
        samples = array.array("h", wav.readframes(wav.getnframes()))
        return wav.getframerate(), list(samples[::channels])


def speech_segments(rate: int, samples: list[int], pause: float) -> list[tuple[float, float]]:
    """Stretches of sound separated by silences of at least ``pause`` seconds."""
    size = max(1, round(rate * FRAME_SECONDS))
    levels = []
    for begin in range(0, len(samples) - size + 1, size):
        chunk = samples[begin : begin + size]
        levels.append(math.sqrt(sum(value * value for value in chunk) / size))
    loud_level = sorted(levels)[int(len(levels) * 0.98)]
    threshold = max(1.0, loud_level * 0.05)
    segments: list[list[float]] = []
    for index, level in enumerate(levels):
        if level <= threshold:
            continue
        start, end = index * FRAME_SECONDS, (index + 1) * FRAME_SECONDS
        if segments and start - segments[-1][1] < pause:
            segments[-1][1] = end
        else:
            segments.append([start, end])
    return [(start, end) for start, end in segments if end - start >= 0.2]


def cut(source: Path, target: Path, start: float, end: float) -> None:
    with wave.open(str(source), "rb") as reader:
        rate = reader.getframerate()
        first = max(0, round(start * rate))
        last = min(reader.getnframes(), round(end * rate))
        reader.setpos(first)
        frames = reader.readframes(max(0, last - first))
        params = reader.getparams()
    with wave.open(str(target), "wb") as writer:
        writer.setparams(params)
        writer.writeframes(frames)


def split_clip(clip: Path, cuts: list[float], total: float, folder: Path) -> list[Path]:
    bounds = [0.0, *cuts, total]
    parts = []
    for number, (first, last) in enumerate(zip(bounds, bounds[1:], strict=False), start=1):
        part = folder / f"part{number}.wav"
        cut(clip, part, first, last)
        parts.append(part)
    return parts


def format_difference(value: float | None) -> str:
    return "   -- " if value is None else f"{value:+6.2f}"


def difference(found: float | None, reference: float) -> float | None:
    return None if found is None else found - reference


def run_setting(
    name: str,
    vad_filter: bool,
    vad_parameters: dict[str, int] | None,
    args: argparse.Namespace,
    script: Script,
    clip: Path,
    parts: list[Path],
    reference: list[tuple[float, float]],
) -> tuple[float, float, float]:
    """Print one setting. Returns (worst whole-vs-split, worst vs sound, mean start error)."""
    transcriber = FasterWhisperTranscriber(
        args.model, device="cpu", vad_filter=vad_filter, vad_parameters=vad_parameters
    )
    ids = [p.id for p in script.paragraphs]

    def align(files: list[Path]) -> AlignmentResult:
        plan = plan_audio(files, ids, AudioMode.PARTS)
        return run_alignment(script, "script", plan, transcriber=transcriber)

    whole, split = align([clip]), align(parts)
    print(f"\n== {name}")
    print("   id    whole: start    end | split: start    end | split-whole: start    end")
    between, against, start_errors = [], [], []
    for index, (one, other) in enumerate(zip(whole.paragraphs, split.paragraphs, strict=True)):
        ref_start, ref_end = reference[index]
        cells = [
            difference(one.start, ref_start),
            difference(one.end, ref_end),
            difference(other.start, ref_start),
            difference(other.end, ref_end),
            None if one.start is None or other.start is None else other.start - one.start,
            None if one.end is None or other.end is None else other.end - one.end,
        ]
        print(f"   {one.id:<4}  " + "  ".join(format_difference(cell) for cell in cells))
        against += [abs(cell) for cell in cells[:4] if cell is not None]
        between += [abs(cell) for cell in cells[4:] if cell is not None]
        start_errors += [abs(cell) for cell in (cells[0], cells[2]) if cell is not None]
    worst_between = max(between, default=math.nan)
    worst_against = max(against, default=math.nan)
    mean_start = sum(start_errors) / len(start_errors) if start_errors else math.nan
    print(
        f"   worst split-vs-whole {worst_between:.2f} s, worst vs the sound {worst_against:.2f} s"
    )
    return worst_between, worst_against, mean_start


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("clip", nargs="?", type=Path, default=ROOT / "tests/fixtures/northwind.wav")
    parser.add_argument("--script", type=Path, default=ROOT / "examples/northwind-script.md")
    parser.add_argument("--model", default="base.en")
    parser.add_argument(
        "--pause", type=float, default=0.7, help="shortest pause between paragraphs"
    )
    args = parser.parse_args()

    script = load_script(args.script, TextMode.QUOTE)
    rate, samples = read_wav(args.clip)
    segments = speech_segments(rate, samples, args.pause)
    wanted = len(script.paragraphs)
    print(f"Clip {args.clip.name}: {len(samples) / rate:.1f} s, {len(segments)} stretches of sound")
    if len(segments) != wanted:
        print(f"Expected {wanted} (one per paragraph). Try --pause with another value.")
        return 1
    for paragraph, (start, end) in zip(script.paragraphs, segments, strict=True):
        print(f"   {paragraph.id:<4} sound from {start:6.2f} to {end:6.2f} s")

    cuts = [(segments[a][1] + segments[a + 1][0]) / 2 for a in (2, 5)]
    import tempfile

    summary = []
    with tempfile.TemporaryDirectory() as folder:
        parts = split_clip(args.clip, cuts, len(samples) / rate, Path(folder))
        for name, vad_filter, vad_parameters in SETTINGS:
            result = run_setting(
                name, vad_filter, vad_parameters, args, script, args.clip, parts, segments
            )
            summary.append((name, *result))
    print("\n== Summary (seconds; smaller is better)")
    print(f"   {'setting':<40} split-vs-whole  vs the sound  mean start error")
    for name, between, against, mean_start in summary:
        print(f"   {name:<40} {between:>13.2f}  {against:>12.2f}  {mean_start:>16.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
