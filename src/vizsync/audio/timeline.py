"""Laying audio parts on one timeline, and reading how long a file is."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from vizsync.errors import AudioError

if TYPE_CHECKING:
    from av.container import InputContainer


@dataclass(frozen=True)
class Part:
    """One audio file on the timeline. ``offset`` and ``duration`` are in seconds."""

    file: Path
    offset: float
    duration: float


def build_timeline(
    files: Sequence[Path],
    durations: Sequence[float],
    *,
    gap: float = 0.0,
    offset: float = 0.0,
) -> list[Part]:
    """Place files one after the other: ``offset[n] = offset + sum(duration[:n]) + n * gap``.

    Args:
        files: The files in playback order.
        durations: The length of each file, in seconds.
        gap: Silence assumed between two consecutive files.
        offset: Time of the first sample, added to every part.
    """
    if len(files) != len(durations):
        raise ValueError("need one duration per file")
    parts: list[Part] = []
    position = offset
    for file, duration in zip(files, durations, strict=True):
        parts.append(Part(file, position, duration))
        position += duration + gap
    return parts


def total_duration(durations: Sequence[float], *, gap: float = 0.0) -> float:
    """Length of the whole timeline: all durations plus the gaps between them."""
    if not durations:
        return 0.0
    return sum(durations) + gap * (len(durations) - 1)


def read_duration(path: Path) -> float:
    """Return the length of an audio file in seconds.

    Raises:
        AudioError: If the file is missing, unreadable or holds no audio.
    """
    import av

    try:
        with av.open(str(path)) as container:
            if not container.streams.audio:
                raise AudioError("The file holds no audio", path=path)
            if container.duration is not None:
                return float(container.duration) / av.time_base
            return _decoded_duration(container)
    except AudioError:
        raise
    except (av.error.FFmpegError, OSError, ValueError) as error:
        raise AudioError(f"Cannot read audio ({error})", path=path) from None


def _decoded_duration(container: "InputContainer") -> float:
    """Length of a file whose container does not say: count the decoded samples."""
    seconds = 0.0
    for frame in container.decode(audio=0):
        seconds += frame.samples / frame.sample_rate
    return seconds
