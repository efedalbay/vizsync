"""Find out where speech recognition stops or fails, step by step, with the real libraries.

Usage: uv run python scripts/diagnose-asr.py [CLIP] [--model base.en] [--timeout 120]

Each step prints how long it took. If a step takes longer than the timeout (a hang inside a
native library does not react to Ctrl+C), the stack of every thread is printed and the program
exits, so the output shows where it was stuck.
"""

import argparse
import faulthandler
import platform
import sys
import time
from pathlib import Path

DEFAULT_CLIP = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "northwind.wav"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("clip", nargs="?", type=Path, default=DEFAULT_CLIP)
    parser.add_argument("--model", default="base.en")
    parser.add_argument("--timeout", type=int, default=120, help="seconds before a step is dumped")
    args = parser.parse_args()

    print(f"Python {sys.version.split()[0]} on {platform.platform()}", flush=True)
    versions = _versions()
    print(versions, flush=True)

    if not args.clip.exists():
        print(f"The clip {args.clip} does not exist.", flush=True)
        return 1

    from faster_whisper import WhisperModel, decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    state: dict[str, object] = {}

    def decode() -> str:
        state["audio"] = decode_audio(str(args.clip))
        return f"{len(state['audio']) / 16000:.1f} s of audio"  # type: ignore[arg-type]

    def vad() -> str:
        chunks = get_speech_timestamps(state["audio"], VadOptions())
        return f"{len(chunks)} speech chunks"

    def load() -> str:
        state["model"] = WhisperModel(args.model, device="cpu", compute_type="int8")
        return f"model {args.model} loaded"

    def transcribe(**options: object):
        def run() -> str:
            segments, _ = state["model"].transcribe(  # type: ignore[attr-defined]
                str(args.clip), language="en", **options
            )
            collected = list(segments)
            words = sum(len(s.words or []) for s in collected)
            return f"{len(collected)} segments, {words} words"

        return run

    steps = [
        ("decode the clip", decode),
        ("voice activity detection", vad),
        ("load the model", load),
        ("transcribe, plain", transcribe()),
        ("transcribe, word times", transcribe(word_timestamps=True)),
        (
            "transcribe, word times + VAD (what vizsync does)",
            transcribe(word_timestamps=True, vad_filter=True),
        ),
    ]
    for number, (name, run) in enumerate(steps, start=1):
        print(f"[{number}/{len(steps)}] {name} ...", flush=True)
        faulthandler.dump_traceback_later(args.timeout, exit=True)
        started = time.perf_counter()
        try:
            result = run()
        except Exception as error:
            faulthandler.cancel_dump_traceback_later()
            print(f"    FAILED: {type(error).__name__}: {error}", flush=True)
            return 1
        faulthandler.cancel_dump_traceback_later()
        print(f"    ok in {time.perf_counter() - started:.1f} s: {result}", flush=True)
    print("All steps finished.", flush=True)
    return 0


def _versions() -> str:
    parts = []
    for name in ("faster_whisper", "ctranslate2", "onnxruntime", "av", "numpy"):
        try:
            module = __import__(name)
            parts.append(f"{name} {getattr(module, '__version__', '?')}")
        except Exception as error:
            parts.append(f"{name} (import failed: {error})")
    return ", ".join(parts)


if __name__ == "__main__":
    sys.exit(main())
