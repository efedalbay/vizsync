"""Cut a piece out of a PCM WAV file, with the standard library only."""

import wave
from pathlib import Path


def cut(source: Path, target: Path, start: float, end: float) -> None:
    """Write the part of ``source`` between ``start`` and ``end`` seconds to ``target``."""
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
