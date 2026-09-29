"""Conversion between seconds and the time text used in output."""

import math
import re

_TIME_PATTERN = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})(?:\.(\d+))?$")


def format_time(seconds: float) -> str:
    """Format seconds as ``MM:SS.s``, or ``H:MM:SS.s`` from one hour up.

    Rounds to the nearest tenth of a second (halves round up).

    Raises:
        ValueError: If ``seconds`` is negative.
    """
    if seconds < 0:
        raise ValueError(f"time cannot be negative: {seconds}")
    tenths_total = math.floor(seconds * 10 + 0.5)
    whole, tenths = divmod(tenths_total, 10)
    minutes_total, secs = divmod(whole, 60)
    hours, minutes = divmod(minutes_total, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}.{tenths}"
    return f"{minutes:02d}:{secs:02d}.{tenths}"


def parse_time(text: str) -> float:
    """Parse ``MM:SS``, ``MM:SS.s``, ``H:MM:SS`` or ``H:MM:SS.s`` into seconds.

    Raises:
        ValueError: If ``text`` is not a valid time.
    """
    match = _TIME_PATTERN.match(text.strip())
    if match is None:
        raise ValueError(f"Invalid time {text!r}: expected MM:SS.s or H:MM:SS.s")
    hours_text, minutes_text, seconds_text, fraction_text = match.groups()
    minutes, secs = int(minutes_text), int(seconds_text)
    if secs >= 60 or (minutes >= 60):
        raise ValueError(f"Invalid time {text!r}: minutes and seconds must be below 60")
    fraction = float(f"0.{fraction_text}") if fraction_text else 0.0
    return int(hours_text or 0) * 3600 + minutes * 60 + secs + fraction
