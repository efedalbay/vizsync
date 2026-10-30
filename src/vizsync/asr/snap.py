"""Hold recognized word times to the speech a voice-activity detector found.

The recognizer often stretches the start of the first word after a long silence back into that
silence, and sometimes the end of a word into the silence after it: such times move inward onto
the speech. It also times a numeral at the end of the time its words take, so the first word of a
stretch of speech can start late: such a start moves back to the start of the speech. Pure
functions, no audio.
"""

from collections.abc import Sequence

from vizsync.asr.base import Word

MIN_WORD_SECONDS = 0.02
"""A snap that would leave a word shorter than this is not made."""

MIN_PULL_SECONDS = 0.3
"""A first word that starts less than this after its stretch of speech keeps its start."""

MAX_PULL_SECONDS = 2.0
"""A first word that starts more than this after its stretch of speech keeps its start: the
speech before it holds something the recognizer did not write."""


def snap_words_to_speech(
    words: Sequence[Word],
    segments: Sequence[tuple[float, float]],
    *,
    tolerance: float = 0.05,
    min_pull: float = MIN_PULL_SECONDS,
    max_pull: float = MAX_PULL_SECONDS,
) -> list[Word]:
    """Hold word times to the speech segments.

    A word belongs to the first segment that ends after the word's start, if it overlaps that
    segment. A start at least ``tolerance`` seconds before the segment start moves to it, and an
    end at least ``tolerance`` seconds after the segment end moves to it; a snap that would leave
    the word shorter than ``MIN_WORD_SECONDS`` is not made. The first word of a segment that
    starts between ``min_pull`` and ``max_pull`` seconds (inclusive) after the segment start moves
    its start back to the segment start, but not before the end of the previous word. A word in a
    silence is kept as it is.

    Args:
        words: Recognized words, sorted by start.
        segments: ``(start, end)`` seconds of speech, sorted and not overlapping.
        tolerance: Smallest difference, in seconds, that is moved inward.
        min_pull: Smallest late start, in seconds, of a first word that is pulled back.
        max_pull: Largest late start, in seconds, of a first word that is pulled back.

    Returns:
        New words in the same order; the input is not changed.
    """
    snapped: list[Word] = []
    index = 0
    claimed = -1
    for word in words:
        while index < len(segments) and segments[index][1] <= word.start:
            index += 1
        if index == len(segments) or segments[index][0] >= word.end:
            snapped.append(word)
            continue
        held = _snap_word(word, segments[index], tolerance)
        if index != claimed:
            claimed = index
            previous_end = snapped[-1].end if snapped else None
            held = _pull_start(held, segments[index][0], previous_end, min_pull, max_pull)
        snapped.append(held)
    return snapped


def _snap_word(word: Word, segment: tuple[float, float], tolerance: float) -> Word:
    segment_start, segment_end = segment
    start = segment_start if segment_start - word.start >= tolerance else word.start
    end = segment_end if word.end - segment_end >= tolerance else word.end
    if (start, end) == (word.start, word.end) or end - start < MIN_WORD_SECONDS:
        return word
    return word.model_copy(update={"start": start, "end": end})


def _pull_start(
    word: Word,
    segment_start: float,
    previous_end: float | None,
    min_pull: float,
    max_pull: float,
) -> Word:
    if not min_pull <= word.start - segment_start <= max_pull:
        return word
    start = segment_start if previous_end is None else max(segment_start, previous_end)
    if start >= word.start:
        return word
    return word.model_copy(update={"start": start})
