"""Convert any recording PyAV can read into a 16 kHz mono 16-bit WAV.

Usage: uv run python scripts/to-wav.py INPUT OUTPUT.wav

The slow tests need a plain PCM WAV (they cut it with the standard library). Windows Sound
Recorder saves .m4a, so convert the recording with this script.
"""

import sys
import wave
from pathlib import Path

import av

RATE = 16000


def convert(source: Path, target: Path) -> float:
    """Write ``source`` as a 16 kHz mono 16-bit WAV at ``target``; return its length in seconds."""
    resampler = av.AudioResampler(format="s16", layout="mono", rate=RATE)
    chunks: list[bytes] = []
    with av.open(str(source)) as container:
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                chunks.append(bytes(converted.planes[0])[: converted.samples * 2])
        for converted in resampler.resample(None):
            chunks.append(bytes(converted.planes[0])[: converted.samples * 2])
    data = b"".join(chunks)
    with wave.open(str(target), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(data)
    return len(data) / 2 / RATE


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: uv run python scripts/to-wav.py INPUT OUTPUT.wav", file=sys.stderr)
        return 1
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    try:
        seconds = convert(source, target)
    except (av.error.FFmpegError, OSError) as error:
        print(f"Could not convert {source}: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {target} ({seconds:.1f} s, 16 kHz mono)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
