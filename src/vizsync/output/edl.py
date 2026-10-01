"""``markers.edl``: one timeline marker per paragraph, for DaVinci Resolve.

Resolve reads markers from an EDL (Timeline > Import > Timeline Markers from EDL). Each
paragraph is an event of one frame at the paragraph start, followed by a comment line that
holds the marker colour, name and length. Resolve places the marker by the event's record
timecode, so the timecode must include the timeline's start (Resolve starts new timelines at
01:00:00:00).

Frames are counted at the real frame rate and labelled at its nominal one: 29.97 fps is counted
at 29.97 and shown as 30 frames per second, without drop-frame.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from vizsync.errors import OutputError

FRAME_RATES = (23.976, 24, 25, 29.97, 30, 50, 59.94, 60)
"""The supported frame rates."""
DEFAULT_FPS = 30.0
DEFAULT_TIMELINE_START = "01:00:00:00"

_TIMECODE = re.compile(r"^(\d{2}):(\d{2}):(\d{2}):(\d{2})$")


@dataclass(frozen=True)
class EdlSettings:
    """Frame rate and timeline start of a marker file."""

    fps: float
    start_frame: int

    @property
    def nominal(self) -> int:
        """Frames per second as written in timecodes (30 for 29.97)."""
        return round(self.fps)

    @classmethod
    def parse(cls, fps: float, timeline_start: str) -> "EdlSettings":
        """Validate ``--fps`` and ``--timeline-start``.

        Raises:
            OutputError: If the frame rate is not supported or the timecode is malformed.
        """
        if fps not in FRAME_RATES:
            choices = ", ".join(f"{rate:g}" for rate in FRAME_RATES)
            raise OutputError(f"Unsupported --fps {fps:g} (use {choices})")
        nominal = round(fps)
        match = _TIMECODE.match(timeline_start.strip())
        if match is None:
            raise OutputError(
                f"Invalid --timeline-start '{timeline_start}' (expected HH:MM:SS:FF, "
                f"for example {DEFAULT_TIMELINE_START})"
            )
        hours, minutes, seconds, frames = (int(part) for part in match.groups())
        if minutes >= 60 or seconds >= 60 or frames >= nominal:
            raise OutputError(
                f"Invalid --timeline-start '{timeline_start}' (minutes and seconds must be below "
                f"60 and frames below {nominal} at {fps:g} fps)"
            )
        return cls(fps, ((hours * 60 + minutes) * 60 + seconds) * nominal + frames)


def to_timecode(seconds: float, settings: EdlSettings) -> str:
    """The timecode ``HH:MM:SS:FF`` of ``seconds`` after the timeline start (nearest frame)."""
    return _timecode_of(settings.start_frame + math.floor(seconds * settings.fps + 0.5), settings)


def build_edl(title: str, markers: Sequence[tuple[str, float]], settings: EdlSettings) -> str:
    """Build the EDL text for ``markers``, given as ``(name, seconds)`` in the order wanted."""
    lines = [f"TITLE: {Path(title).stem}", "FCM: NON-DROP FRAME"]
    for number, (name, seconds) in enumerate(markers, start=1):
        frame = settings.start_frame + math.floor(seconds * settings.fps + 0.5)
        begin, end = _timecode_of(frame, settings), _timecode_of(frame + 1, settings)
        lines += [
            "",
            f"{number:03d}  001      V     C        {begin} {end} {begin} {end}  ",
            f" |C:ResolveColorBlue |M:{name} |D:1",
        ]
    return "\n".join(lines) + "\n"


def write_edl(text: str, path: Path) -> None:
    """Write ``markers.edl`` as UTF-8.

    Raises:
        OutputError: If the file cannot be written.
    """
    try:
        with path.open("w", encoding="utf-8", newline="\n") as file:
            file.write(text)
    except OSError as error:
        raise OutputError(f"Cannot write the file ({error.strerror})", path=path) from None


def _timecode_of(frame: int, settings: EdlSettings) -> str:
    seconds_total, frames = divmod(frame, settings.nominal)
    minutes_total, seconds = divmod(seconds_total, 60)
    hours, minutes = divmod(minutes_total, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"
