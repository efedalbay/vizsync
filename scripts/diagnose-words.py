"""Show how the first words of a recording are recognized and matched to the script.

Usage: uv run python scripts/diagnose-words.py AUDIO --script SCRIPT [--text quote|inline]
       [--paragraph P1] [--model small.en] [--words 12]

For one audio file prints, with times: where the voice-activity detector finds speech, the first
recognized words as the model wrote them (before and after word times are held to the speech),
and every normalized word of the paragraph with the recognized word it was matched to. The start
vizsync reports for the paragraph is printed last. Needs the speech model.
"""

import argparse
from pathlib import Path

from vizsync.asr.faster_whisper import FasterWhisperTranscriber
from vizsync.audio.speech import speech_segments
from vizsync.match.aligner import align
from vizsync.match.normalize import normalize_text, normalize_words
from vizsync.match.spans import compute_spans
from vizsync.script.models import TextMode
from vizsync.script.parser import load_script


def clock(seconds: float) -> str:
    return f"{seconds:7.2f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("audio", type=Path)
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--text", choices=[mode.value for mode in TextMode], default="quote")
    parser.add_argument("--paragraph", default="P1")
    parser.add_argument("--model", default="small.en")
    parser.add_argument("--words", type=int, default=12)
    args = parser.parse_args()

    script = load_script(args.script, TextMode(args.text))
    paragraphs = script.paragraphs
    chosen = next((p for p in paragraphs if p.id == args.paragraph), None)
    if chosen is None:
        raise SystemExit(f"{args.paragraph} is not in the script")

    print("== speech found by the voice-activity detector (first 4 stretches) ==")
    for start, end in speech_segments(args.audio)[:4]:
        print(f"  {clock(start)} - {clock(end)}")

    raw = FasterWhisperTranscriber(args.model, snap_to_speech=False).transcribe(
        args.audio, language="en"
    )
    held = FasterWhisperTranscriber(args.model).transcribe(args.audio, language="en")
    for title, words in (("as the model wrote them", raw), ("held to the speech", held)):
        print(f"\n== first {args.words} recognized words, {title} ==")
        print("  " + " | ".join(f"{w.text} {w.start:.2f}-{w.end:.2f}" for w in words[: args.words]))
    print(f"\n== after normalization (first {args.words}) ==")
    normalized = normalize_words(held)
    first = normalized[: args.words]
    print("  " + " | ".join(f"{w.text} {w.start:.2f}-{w.end:.2f}" for w in first))

    print(f"\n== {chosen.id}: script words and the recognized word each was matched to ==")
    script_words = [normalize_text(p.text) for p in paragraphs]
    matches = align(
        [word for words in script_words for word in words], [w.text for w in normalized]
    )
    position = sum(len(words) for words in script_words[: paragraphs.index(chosen)])
    for offset, word in enumerate(script_words[paragraphs.index(chosen)][: args.words]):
        match = matches[position + offset]
        if match is None:
            print(f"  {word:<14} not matched")
        else:
            heard = normalized[match.recognized_index]
            print(
                f"  {word:<14} -> {heard.text:<14} {heard.start:.2f}-{heard.end:.2f}"
                f"  similarity {match.similarity:.2f}"
            )
    spans = compute_spans(paragraphs, held)
    span = next(s for s in spans if s.id == chosen.id)
    print(f"\n== reported: {span.id} {span.status.value} start {span.start} end {span.end} ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
