"""Show what the speech model heard around the end of the fixture clip, whole and as part 3.

Usage: uv run python scripts/diagnose-split.py [CLIP] [--script SCRIPT] [--model base.en]

Cuts the clip into three parts like ``test_three_parts_give_the_same_times``, then for the whole
clip and for the last part prints the recognized words of the last paragraphs (as the model wrote
them and after normalization) and, for each of those paragraphs, every normalized script word with
the time of the recognized word it was matched to. Needs the speech model.
"""

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "slow"))

from wavcut import cut  # noqa: E402

from vizsync.asr.faster_whisper import FasterWhisperTranscriber  # noqa: E402
from vizsync.audio.inputs import AudioMode, plan_audio  # noqa: E402
from vizsync.match.normalize import normalize_text, normalize_words  # noqa: E402
from vizsync.pipeline import AlignmentResult, run_alignment  # noqa: E402
from vizsync.script.models import Script, TextMode  # noqa: E402
from vizsync.script.parser import load_script  # noqa: E402

SHOWN = ("P6", "P7", "P8")


def align(script: Script, files: list[Path], transcriber: FasterWhisperTranscriber):
    plan = plan_audio(files, [p.id for p in script.paragraphs], AudioMode.PARTS)
    return run_alignment(script, "script", plan, transcriber=transcriber)


def show_words(title: str, path: Path, transcriber: FasterWhisperTranscriber, after: float) -> None:
    words = [w for w in transcriber.transcribe(path, language="en") if w.start >= after]
    print(f"\n== {title}: recognized words from {after:.2f} s (as written by the model) ==")
    print("  " + " | ".join(f"{w.text.strip()} {w.start:.2f}-{w.end:.2f}" for w in words))
    print(f"== {title}: after normalization ==")
    print("  " + " | ".join(f"{w.text} {w.start:.2f}-{w.end:.2f}" for w in normalize_words(words)))


def show_matches(title: str, result: AlignmentResult) -> None:
    print(f"\n== {title}: the script words of {', '.join(SHOWN)} and where they were matched ==")
    for paragraph in result.paragraphs:
        if paragraph.id not in SHOWN:
            continue
        print(
            f"  {paragraph.id} {paragraph.status.value} confidence {paragraph.confidence:.2f}"
            f" start {paragraph.start} end {paragraph.end}"
        )
        for word, time in zip(normalize_text(paragraph.text), paragraph.word_times, strict=False):
            shown = "not matched" if time is None else f"{time[0]:.2f}-{time[1]:.2f}"
            print(f"      {word:<14} {shown}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("clip", nargs="?", type=Path, default=ROOT / "tests/fixtures/northwind.wav")
    parser.add_argument("--script", type=Path, default=ROOT / "examples/northwind-script.md")
    parser.add_argument("--model", default="base.en")
    args = parser.parse_args()

    script = load_script(args.script, TextMode.QUOTE)
    transcriber = FasterWhisperTranscriber(args.model)
    whole = align(script, [args.clip], transcriber)
    by_id = {p.id: p for p in whole.paragraphs}
    cuts = []
    for before, after in (("P3", "P4"), ("P6", "P7")):
        end, start = by_id[before].end, by_id[after].start
        assert end is not None and start is not None
        cuts.append((end + start) / 2)
    bounds = [0.0, *cuts, whole.total_duration]
    with tempfile.TemporaryDirectory() as folder:
        parts = []
        for number, (first, last) in enumerate(zip(bounds, bounds[1:], strict=False), start=1):
            part = Path(folder) / f"part{number}.wav"
            cut(args.clip, part, first, last)
            parts.append(part)
        split = align(script, parts, transcriber)
        show_words("whole clip", args.clip, transcriber, cuts[1])
        show_words("part 3", parts[2], transcriber, 0.0)
    show_matches("whole clip", whole)
    show_matches("3 parts", split)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
