"""Spot paragraphs that take far longer than their words suggest.

A paragraph that spans minutes for a dozen words usually means the script text was read more
than once, or out of order, and the aligner picked words from different places. The check
compares each paragraph's seconds per word with the median of all paragraphs, so a slow
narrator is not flagged, only a paragraph that is slow compared with the others.
"""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

SLOW_FACTOR = 3.0
"""A paragraph is slow if its seconds per word exceed this many times the median."""
MIN_SECONDS = 5.0
"""Shorter paragraphs are never flagged: a single pause would be enough to trip them."""
MIN_PARAGRAPHS = 3
"""With fewer paragraphs there is no reliable median."""


@dataclass(frozen=True)
class Pace:
    """A found paragraph: how many words the script has for it and how long it spans."""

    id: str
    words: int
    seconds: float


def slow_paragraphs(paces: Sequence[Pace]) -> list[str]:
    """Return the identifiers of paragraphs much slower than the median, in the order given."""
    usable = [pace for pace in paces if pace.words > 0 and pace.seconds > 0]
    if len(usable) < MIN_PARAGRAPHS:
        return []
    median = statistics.median(pace.seconds / pace.words for pace in usable)
    return [
        pace.id
        for pace in usable
        if pace.seconds >= MIN_SECONDS and pace.seconds / pace.words > SLOW_FACTOR * median
    ]
