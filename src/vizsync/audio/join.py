"""Joining paragraph recordings into one narration file.

Text-to-speech tools write one WAV per paragraph. To edit them as a single audio track, and so
that the times in ``timing.json`` match that track exactly, the files are laid one after the other
with a silence between them: a short one between paragraphs and a longer one where a new chapter
begins.

The samples are copied unchanged: nothing is decoded, resampled or encoded again. Only silence is
added, and optionally the silence at the start and end of each file is cut away, in whole samples.
Only plain PCM WAV files can be joined this way, and all of them must have the same sample rate,
channel count and sample size. Gaps are rounded to whole samples, and every time is computed from
the sample counts, so the times and the file agree to the sample.
"""

import contextlib
import math
import os
import wave
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from vizsync.errors import AudioError, OutputError

DEFAULT_PARAGRAPH_GAP = 0.6
"""Seconds of silence between two paragraphs of a chapter."""
DEFAULT_CHAPTER_GAP = 1.2
"""Seconds of silence where a new chapter begins."""
JOINED_NAME = "narration.wav"
"""File name of the joined narration, in the output folder."""
TRIM_PAD_SECONDS = 0.05
"""Silence kept before the first and after the last speech of a trimmed file."""
_CHUNK_FRAMES = 65536

SpeechBounds = Callable[[Path], tuple[float, float] | None]
"""``file`` to ``(first speech second, last speech second)``, or None if it holds no speech."""


@dataclass(frozen=True)
class WavFormat:
    """What must be equal in every file that is joined."""

    channels: int
    sample_width: int
    frame_rate: int

    def describe(self) -> str:
        """For messages: ``44100 Hz, mono, 16-bit``."""
        channels = "mono" if self.channels == 1 else f"{self.channels} channels"
        return f"{self.frame_rate} Hz, {channels}, {self.sample_width * 8}-bit"


@dataclass(frozen=True)
class JoinEntry:
    """One paragraph in the joined file.

    The frames ``first_frame`` up to ``last_frame`` of ``source`` are copied to
    ``offset_frames`` of the joined file.
    """

    paragraph_id: str
    source: Path
    first_frame: int
    last_frame: int
    offset_frames: int

    @property
    def frames(self) -> int:
        """Length of the copied part, in frames."""
        return self.last_frame - self.first_frame


@dataclass(frozen=True)
class JoinLayout:
    """Where every paragraph goes in the joined file."""

    target: Path
    format: WavFormat
    entries: list[JoinEntry]
    total_frames: int
    warnings: list[str]

    @property
    def total_seconds(self) -> float:
        """Length of the joined file."""
        return self.total_frames / self.format.frame_rate


def read_wav_info(path: Path) -> tuple[WavFormat, int]:
    """Return the format and the number of frames of a PCM WAV file.

    Raises:
        AudioError: If the file cannot be read or is not a plain PCM WAV.
    """
    try:
        with wave.open(str(path), "rb") as wav:
            info = WavFormat(wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
            return info, wav.getnframes()
    except (wave.Error, EOFError):
        raise AudioError(
            "Joining needs plain PCM WAV files; convert this one first "
            "(for example with 'uv run python scripts/to-wav.py INPUT OUTPUT.wav')",
            path=path,
        ) from None
    except OSError as error:
        raise AudioError(f"Cannot read the file ({error.strerror})", path=path) from None


def trim_range(
    total_frames: int, frame_rate: int, bounds: tuple[float, float], pad: float
) -> tuple[int, int]:
    """The frames to keep: from ``pad`` before the first speech to ``pad`` after the last.

    Rounds outwards and never leaves the file.
    """
    start, end = bounds
    first = math.floor(round((start - pad) * frame_rate, 6))
    last = math.ceil(round((end + pad) * frame_rate, 6))
    return max(0, first), min(total_frames, last)


def plan_join(
    paragraphs: Sequence[tuple[str, int]],
    files: Mapping[str, Path],
    *,
    target: Path,
    paragraph_gap: float,
    chapter_gap: float,
    speech_bounds: SpeechBounds | None = None,
) -> JoinLayout:
    """Work out where each paragraph file goes. Reads the headers of the files, never the samples.

    Args:
        paragraphs: ``(paragraph id, chapter number)`` in script order.
        files: The file of each paragraph; a paragraph without one is left out.
        target: The joined file to be written.
        paragraph_gap: Seconds of silence between two paragraphs of a chapter.
        chapter_gap: Seconds of silence where a new chapter begins.
        speech_bounds: When given, the silence at the start and end of each file is cut away
            (keeping ``TRIM_PAD_SECONDS``) using the speech this finds.

    Raises:
        AudioError: If a file cannot be read, is not a plain PCM WAV, differs in format from the
            first one, or is the file to be written.
    """
    found = [(name, chapter, files[name]) for name, chapter in paragraphs if name in files]
    infos = [(name, chapter, path, *read_wav_info(path)) for name, chapter, path in found]
    shared = _shared_format(infos)
    rate = shared.frame_rate if shared else 1
    entries: list[JoinEntry] = []
    warnings: list[str] = []
    position = 0
    previous_chapter: int | None = None
    for name, chapter, path, _, frames in infos:
        if path.resolve() == target.resolve():
            raise AudioError("This file would be overwritten by the joined narration", path=path)
        first, last = 0, frames
        if speech_bounds is not None:
            bounds = speech_bounds(path)
            if bounds is None:
                warnings.append(f"{path.name}: no speech found, not trimmed.")
            else:
                first, last = trim_range(frames, rate, bounds, TRIM_PAD_SECONDS)
        if previous_chapter is not None:
            gap = chapter_gap if chapter != previous_chapter else paragraph_gap
            position += round(gap * rate)
        entries.append(JoinEntry(name, path, first, last, position))
        position += last - first
        previous_chapter = chapter
    return JoinLayout(target, shared or WavFormat(1, 2, 1), entries, position, warnings)


def write_joined(layout: JoinLayout, target: Path) -> None:
    """Write the joined file: the samples of every entry and silence between them.

    Raises:
        OutputError: If the file or its folder cannot be written.
        AudioError: If a source file cannot be read.
    """
    silence = _silence_byte(layout.format.sample_width)
    frame_size = layout.format.sample_width * layout.format.channels
    temporary = target.with_name(target.name + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(temporary), "wb") as out:
            out.setnchannels(layout.format.channels)
            out.setsampwidth(layout.format.sample_width)
            out.setframerate(layout.format.frame_rate)
            written = 0
            for entry in layout.entries:
                _write_silence(out, entry.offset_frames - written, silence, frame_size)
                _copy_frames(out, entry)
                written = entry.offset_frames + entry.frames
        os.replace(temporary, target)
    except OSError as error:
        _discard(temporary)
        raise OutputError(f"Cannot write the file ({error.strerror})", path=target) from None
    except BaseException:
        _discard(temporary)
        raise


def _discard(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)


def _shared_format(infos: Sequence[tuple[str, int, Path, WavFormat, int]]) -> WavFormat | None:
    if not infos:
        return None
    first_path, first_format = infos[0][2], infos[0][3]
    for _, _, path, found, _ in infos[1:]:
        if found != first_format:
            raise AudioError(
                f"{path.name} is {found.describe()}, but {first_path.name} is "
                f"{first_format.describe()}; the files to join must all have one format",
                path=path,
            )
    return first_format


def _silence_byte(sample_width: int) -> int:
    """8-bit WAV samples are unsigned, so their silence is the middle value; others are 0."""
    return 0x80 if sample_width == 1 else 0


def _write_silence(out: wave.Wave_write, frames: int, silence: int, frame_size: int) -> None:
    remaining = frames
    while remaining > 0:
        count = min(remaining, _CHUNK_FRAMES)
        out.writeframes(bytes([silence]) * (count * frame_size))
        remaining -= count


def _copy_frames(out: wave.Wave_write, entry: JoinEntry) -> None:
    try:
        with wave.open(str(entry.source), "rb") as source:
            source.setpos(entry.first_frame)
            remaining = entry.frames
            while remaining > 0:
                data = source.readframes(min(remaining, _CHUNK_FRAMES))
                if not data:
                    raise AudioError(
                        "The file ends earlier than its header says", path=entry.source
                    )
                out.writeframes(data)
                remaining -= len(data) // (source.getsampwidth() * source.getnchannels())
    except (wave.Error, EOFError):
        raise AudioError("Cannot read the samples of the file", path=entry.source) from None
