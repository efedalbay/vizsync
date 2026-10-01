"""From an alignment to paragraph start, end, confidence and status.

A paragraph that is found spans from the start of its first matched word to the end of its
last matched word. Unmatched script words at either edge bias that span inward, so it is
widened by (unmatched edge words x the paragraph's median matched-word duration), but only
over recognized words that nothing matched: time where the recognizer heard something the
script could not account for. It never extends into silence and never past the matched words
of the nearest found neighbour; missing paragraphs are not neighbours. The first and last
found paragraphs are bounded by the first and last recognized words. When two neighbours both
extend into the same unmatched words and would overlap, the room between them is shared in
proportion to how far each wanted to move.

A missing paragraph never gets times.
"""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from vizsync.asr.base import Word
from vizsync.match.aligner import WordMatch, align
from vizsync.match.normalize import normalize_text, normalize_words
from vizsync.script.models import Paragraph

DEFAULT_MIN_CONFIDENCE = 0.8
"""Below this confidence a found paragraph is ``low_confidence``."""
MISSING_MATCHED_FRACTION = 0.3
"""Below this fraction of matched script words a paragraph is ``missing``."""


class ParagraphStatus(StrEnum):
    """How well a paragraph was found in the audio."""

    OK = "ok"
    LOW_CONFIDENCE = "low_confidence"
    MISSING = "missing"


@dataclass(frozen=True)
class ParagraphSpan:
    """Where one paragraph is in the audio. ``start``/``end`` are ``None`` when missing."""

    id: str
    start: float | None
    end: float | None
    confidence: float
    status: ParagraphStatus


def compute_spans(
    paragraphs: Sequence[Paragraph],
    words: Sequence[Word],
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> list[ParagraphSpan]:
    """Find every paragraph in the recognized words.

    Args:
        paragraphs: The script paragraphs, in script order.
        words: Recognized words in time order, on one timeline. Spans use the same timeline.
        min_confidence: Found paragraphs below this confidence are ``low_confidence``.

    Returns:
        One span per paragraph, in script order.
    """
    paragraph_words = [normalize_text(paragraph.text) for paragraph in paragraphs]
    recognized = normalize_words(words)
    matches = align(
        [word for paragraph in paragraph_words for word in paragraph],
        [word.text for word in recognized],
    )
    return spans_from_alignment(
        [paragraph.id for paragraph in paragraphs],
        split_matches(matches, [len(paragraph) for paragraph in paragraph_words]),
        recognized,
        min_confidence=min_confidence,
    )


def split_matches(
    matches: Sequence[WordMatch | None], word_counts: Sequence[int]
) -> list[list[WordMatch | None]]:
    """Cut the alignment of the whole script into one list per paragraph."""
    if sum(word_counts) != len(matches):
        raise ValueError("word counts must add up to the number of matches")
    result: list[list[WordMatch | None]] = []
    position = 0
    for count in word_counts:
        result.append(list(matches[position : position + count]))
        position += count
    return result


def paragraph_confidence(matches: Sequence[WordMatch | None]) -> float:
    """Matched script words weighted by similarity, divided by all script words (0 if none)."""
    if not matches:
        return 0.0
    return sum(match.similarity for match in matches if match is not None) / len(matches)


def paragraph_status(
    matches: Sequence[WordMatch | None], *, min_confidence: float
) -> ParagraphStatus:
    """Classify a paragraph from the matches of its script words."""
    matched = sum(match is not None for match in matches)
    if matched == 0 or matched / len(matches) < MISSING_MATCHED_FRACTION:
        return ParagraphStatus.MISSING
    if paragraph_confidence(matches) < min_confidence:
        return ParagraphStatus.LOW_CONFIDENCE
    return ParagraphStatus.OK


def spans_from_alignment(
    paragraph_ids: Sequence[str],
    paragraph_matches: Sequence[Sequence[WordMatch | None]],
    words: Sequence[Word],
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> list[ParagraphSpan]:
    """Build paragraph spans from per-paragraph matches.

    Args:
        paragraph_ids: Paragraph identifiers, in script order.
        paragraph_matches: For each paragraph, the match of each of its script words.
        words: The recognized words the matches point into, in time order.
        min_confidence: Found paragraphs below this confidence are ``low_confidence``.
    """
    if len(paragraph_ids) != len(paragraph_matches):
        raise ValueError("need one match list per paragraph")
    statuses = [paragraph_status(m, min_confidence=min_confidence) for m in paragraph_matches]
    found = {
        index: _found_paragraph(paragraph_matches[index], words)
        for index, status in enumerate(statuses)
        if status is not ParagraphStatus.MISSING
    }
    _refine_boundaries(list(found.values()), words)
    spans = []
    for index, paragraph_id in enumerate(paragraph_ids):
        paragraph = found.get(index)
        spans.append(
            ParagraphSpan(
                id=paragraph_id,
                start=None if paragraph is None else paragraph.start,
                end=None if paragraph is None else paragraph.end,
                confidence=paragraph_confidence(paragraph_matches[index]),
                status=statuses[index],
            )
        )
    return spans


@dataclass
class _Found:
    """A found paragraph while its boundaries are refined."""

    first_index: int
    last_index: int
    start: float
    end: float
    unmatched_before: int
    unmatched_after: int
    median_duration: float
    move_start: float = 0.0
    move_end: float = 0.0


def _found_paragraph(matches: Sequence[WordMatch | None], words: Sequence[Word]) -> _Found:
    positions = [position for position, match in enumerate(matches) if match is not None]
    indices = [match.recognized_index for match in matches if match is not None]
    return _Found(
        first_index=indices[0],
        last_index=indices[-1],
        start=words[indices[0]].start,
        end=words[indices[-1]].end,
        unmatched_before=positions[0],
        unmatched_after=len(matches) - 1 - positions[-1],
        median_duration=statistics.median(words[i].end - words[i].start for i in indices),
    )


def _refine_boundaries(found: list[_Found], words: Sequence[Word]) -> None:
    """Widen the found paragraphs (in script order) over unmatched recognized words."""
    for position, paragraph in enumerate(found):
        unclaimed_from = found[position - 1].last_index + 1 if position > 0 else 0
        unclaimed_to = found[position + 1].first_index - 1 if position + 1 < len(found) else None
        if unclaimed_to is None:
            unclaimed_to = len(words) - 1
        if unclaimed_from < paragraph.first_index:
            wanted = paragraph.unmatched_before * paragraph.median_duration
            room = paragraph.start - words[unclaimed_from].start
            paragraph.move_start = max(0.0, min(wanted, room))
        if paragraph.last_index < unclaimed_to:
            wanted = paragraph.unmatched_after * paragraph.median_duration
            room = words[unclaimed_to].end - paragraph.end
            paragraph.move_end = max(0.0, min(wanted, room))
    for before, after in zip(found, found[1:], strict=False):
        _share_room(before, after)
    for paragraph in found:
        paragraph.start -= paragraph.move_start
        paragraph.end += paragraph.move_end


def _share_room(before: _Found, after: _Found) -> None:
    """Keep two neighbours from overlapping: share the room between them by how far each moves."""
    room = max(0.0, after.start - before.end)
    total = before.move_end + after.move_start
    if total > room:
        before.move_end = room * before.move_end / total
        after.move_start = room * after.move_start / total
