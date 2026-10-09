"""Hold recognized word times to the speech a voice-activity detector found.

The recognizer often stretches the start of the first word after a long silence back into that
silence, and sometimes the end of a word into the silence after it. Pure functions, no audio.
"""

from collections.abc import Sequence

from vizsync.asr.base import Word

MIN_WORD_SECONDS = 0.02
"""A snap that would leave a word shorter than this is not made."""


def snap_words_to_speech(
    words: Sequence[Word],
    segments: Sequence[tuple[float, float]],
    *,
    tolerance: float = 0.05,
) -> list[Word]:
    """Move word starts later and word ends earlier onto the speech segments.

    A word belongs to the first segment that ends after the word's start. If the word overlaps
    that segment, a start at least ``tolerance`` seconds before the segment start moves to it,
    and an end at least ``tolerance`` seconds after the segment end moves to it. A word in a
    silence, or one a snap would leave shorter than ``MIN_WORD_SECONDS``, is kept as it is.

    Args:
        words: Recognized words, sorted by start.
        segments: ``(start, end)`` seconds of speech, sorted and not overlapping.
        tolerance: Smallest difference, in seconds, that is corrected.

    Returns:
        New words in the same order; the input is not changed.
    """
    snapped: list[Word] = []
    index = 0
    for word in words:
        while index < len(segments) and segments[index][1] <= word.start:
            index += 1
        if index == len(segments):
            snapped.append(word)
            continue
        snapped.append(_snap_word(word, segments[index], tolerance))
    return snapped


def _snap_word(word: Word, segment: tuple[float, float], tolerance: float) -> Word:
    segment_start, segment_end = segment
    if segment_start >= word.end:
        return word
    start = segment_start if segment_start - word.start >= tolerance else word.start
    end = segment_end if word.end - segment_end >= tolerance else word.end
    if (start, end) == (word.start, word.end) or end - start < MIN_WORD_SECONDS:
        return word
    return word.model_copy(update={"start": start, "end": end})
