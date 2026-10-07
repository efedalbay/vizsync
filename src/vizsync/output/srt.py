"""``captions.srt``: the script text as subtitles, timed by the speech.

The text is the aligned text of each paragraph (already without source marks such as ``[5]``),
so it is exactly what the script says, unlike automatic captions. Each paragraph becomes one or
more cues:

- A cue is a sentence, or a part of a long one. A cue holds at most two lines of at most 42
  characters; a longer sentence is cut at the comma (or other pause mark) that balances the parts
  best, and failing that between words. A cue also lasts at most 7 seconds.
- A cue shorter than a second is lengthened into free time, never into the next cue.
- A cue starts when its first word was spoken and ends when its last was, using the times of the
  words the aligner matched. Words that matched nothing, and paragraphs that were never
  recognized (one file per paragraph), take their time in proportion to their length between the
  nearest known times, or between the start and end of the paragraph.
- The first cue of a paragraph starts, and the last ends, with the paragraph.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from vizsync.errors import OutputError
from vizsync.match.normalize import normalize_text
from vizsync.pipeline import ParagraphResult

MAX_LINE_CHARS = 42
MAX_LINES = 2
MIN_CUE_SECONDS = 1.0
MAX_CUE_SECONDS = 7.0

_SENTENCE_END = re.compile(r"[.!?…][\"'”’)\]»]*$")
_PAUSE_MARK = re.compile(r"[,;:—–][\"'”’)\]»]*$")
FAIR_SHARE = 0.2
"""A cut after a pause mark is only taken if both parts keep at least this share of the whole."""
_PAUSE_BONUS = 15.0


@dataclass(frozen=True)
class Cue:
    """One subtitle: its time in seconds and its text (lines separated by a newline)."""

    start: float
    end: float
    text: str
    paragraph: str = field(default="", compare=False)
    """The paragraph the cue belongs to; cues of one paragraph may be joined or share time."""


def build_captions(paragraphs: Sequence[ParagraphResult]) -> list[Cue]:
    """The cues for every found paragraph, in order and without overlap."""
    cues: list[Cue] = []
    for paragraph in paragraphs:
        if paragraph.start is None or paragraph.end is None or not paragraph.text.split():
            continue
        cues += _paragraph_cues(paragraph, paragraph.start, paragraph.end)
    return _tidy(cues)


def format_srt_time(seconds: float) -> str:
    """``HH:MM:SS,mmm``, rounded to the millisecond (halves round up)."""
    total = math.floor(seconds * 1000 + 0.5)
    whole, millis = divmod(total, 1000)
    minutes, secs = divmod(whole, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_srt(cues: Sequence[Cue]) -> str:
    """The SRT text: numbered cues separated by blank lines. Empty for no cues."""
    blocks = [
        f"{number}\n{format_srt_time(cue.start)} --> {format_srt_time(cue.end)}\n{cue.text}\n"
        for number, cue in enumerate(cues, start=1)
    ]
    return "\n".join(blocks)


def write_srt(text: str, path: Path) -> None:
    """Write ``captions.srt`` as UTF-8 without a byte order mark.

    Raises:
        OutputError: If the file cannot be written.
    """
    try:
        with path.open("w", encoding="utf-8", newline="\n") as file:
            file.write(text)
    except OSError as error:
        raise OutputError(f"Cannot write the file ({error.strerror})", path=path) from None


Times = list[tuple[float, float]]


def _paragraph_cues(paragraph: ParagraphResult, start: float, end: float) -> list[Cue]:
    tokens = paragraph.text.split()
    times = _token_times(tokens, paragraph, start, end)
    cues = [
        Cue(times[first][0], times[last - 1][1], _lines(tokens[first:last]), paragraph.id)
        for first, last in _pieces(tokens, times)
    ]
    cues[0] = replace(cues[0], start=start)
    cues[-1] = replace(cues[-1], end=end)
    return cues


def _token_times(
    tokens: Sequence[str], paragraph: ParagraphResult, start: float, end: float
) -> Times:
    """A ``(start, end)`` for every whitespace-separated token of the text."""
    counts = [len(normalize_text(token)) for token in tokens]
    known: list[tuple[float, float] | None] = [None] * len(tokens)
    if len(paragraph.word_times) == sum(counts):
        position = 0
        for index, count in enumerate(counts):
            matched = [w for w in paragraph.word_times[position : position + count] if w]
            if matched:
                known[index] = (matched[0][0], matched[-1][1])
            position += count
    result: Times = [(0.0, 0.0)] * len(tokens)
    index, left = 0, start
    while index < len(tokens):
        current = known[index]
        if current is not None:
            result[index] = current
            left = current[1]
            index += 1
            continue
        stop = index
        while stop < len(tokens) and known[stop] is None:
            stop += 1
        following = known[stop] if stop < len(tokens) else None
        right = following[0] if following is not None else end
        weights = [len(token) + 1 for token in tokens[index:stop]]
        span = max(0.0, right - left)
        clock = left
        for offset, weight in enumerate(weights):
            share = span * weight / sum(weights)
            result[index + offset] = (clock, clock + share)
            clock += share
        index = stop
    return result


def _pieces(tokens: Sequence[str], times: Times) -> list[tuple[int, int]]:
    """Cut the tokens into cue-sized ranges: sentences first, then by length and duration."""
    pieces: list[tuple[int, int]] = []
    first = 0
    for index, token in enumerate(tokens):
        if _SENTENCE_END.search(token) or index == len(tokens) - 1:
            pieces += _fit(tokens, times, first, index + 1)
            first = index + 1
    return pieces


def _fit(tokens: Sequence[str], times: Times, first: int, last: int) -> list[tuple[int, int]]:
    too_long_text = _two_lines(tokens[first:last]) is None
    too_long_time = times[last - 1][1] - times[first][0] > MAX_CUE_SECONDS
    if last - first == 1 or not (too_long_text or too_long_time):
        return [(first, last)]
    cut = _best_cut(tokens, times, first, last, by_text=too_long_text)
    return _fit(tokens, times, first, cut) + _fit(tokens, times, cut, last)


def _best_cut(tokens: Sequence[str], times: Times, first: int, last: int, *, by_text: bool) -> int:
    """Where to cut: after a pause mark if one leaves both parts a fair share, else evenly.

    The parts are measured in characters when the text is too long, in seconds when the cue is
    too long to stay on screen.
    """

    def size(begin: int, stop: int) -> float:
        if by_text:
            return float(len(" ".join(tokens[begin:stop])))
        return times[stop - 1][1] - times[begin][0]

    total = size(first, last)
    cuts = list(range(first + 1, last))
    fair = [k for k in cuts if min(size(first, k), size(k, last)) >= FAIR_SHARE * total]
    candidates = fair or cuts
    paused = [k for k in candidates if _PAUSE_MARK.search(tokens[k - 1])]
    return min(paused or candidates, key=lambda k: abs(size(first, k) - size(k, last)))


def _two_lines(tokens: Sequence[str]) -> list[str] | None:
    """The text on at most two lines of at most 42 characters, or None if it cannot be."""
    text = " ".join(tokens)
    if len(text) <= MAX_LINE_CHARS or len(tokens) == 1:
        return [text]
    options: list[tuple[float, list[str]]] = []
    for cut in range(1, len(tokens)):
        first, second = " ".join(tokens[:cut]), " ".join(tokens[cut:])
        if len(first) <= MAX_LINE_CHARS and len(second) <= MAX_LINE_CHARS:
            bonus = _PAUSE_BONUS / 3 if _PAUSE_MARK.search(tokens[cut - 1]) else 0.0
            options.append((abs(len(first) - len(second)) - bonus, [first, second]))
    return min(options, key=lambda option: option[0])[1] if options else None


def _lines(tokens: Sequence[str]) -> str:
    lines = _two_lines(tokens)
    return "\n".join(lines) if lines else " ".join(tokens)


def _tidy(cues: list[Cue]) -> list[Cue]:
    """No overlap, and no cue shorter than a second where there is a way to lengthen it.

    A short cue is lengthened into the free time after it; then joined to a neighbour of its
    paragraph if the text still fits two lines; then given time from the next cue of its
    paragraph while that one keeps a second. The last cue may run past the end of its paragraph.
    """
    cues = [
        replace(cue, end=min(cue.end, cues[index + 1].start) if index + 1 < len(cues) else cue.end)
        for index, cue in enumerate(cues)
    ]
    cues = [replace(cue, end=max(cue.end, cue.start)) for cue in cues]
    index = 0
    while index < len(cues):
        cue = cues[index]
        if cue.end - cue.start >= MIN_CUE_SECONDS - _EPSILON:
            index += 1
            continue
        wanted = cue.start + MIN_CUE_SECONDS
        following = cues[index + 1] if index + 1 < len(cues) else None
        if following is None:
            cues[index] = replace(cue, end=wanted)
            index += 1
        elif following.start - cue.end > _EPSILON:
            cues[index] = replace(cue, end=min(wanted, following.start))
        elif (joined := _joined_with_neighbour(cues, index)) is not None:
            first, cues[first : first + 2] = joined[0], [joined[1]]
            index = first
        elif (
            _same_paragraph(cue, following) and following.end - wanted >= MIN_CUE_SECONDS - _EPSILON
        ):
            cues[index] = replace(cue, end=wanted)
            cues[index + 1] = replace(following, start=wanted)
            index += 1
        else:
            index += 1
    return cues


def _same_paragraph(first: Cue, second: Cue) -> bool:
    return bool(first.paragraph) and first.paragraph == second.paragraph


def _joined_with_neighbour(cues: list[Cue], index: int) -> tuple[int, Cue] | None:
    """The short cue joined to the shorter neighbour of its paragraph, if that fits in a cue.

    Returns the index of the first of the two joined cues and the joined cue.
    """
    options: list[tuple[float, int, Cue]] = []
    for other in (index - 1, index + 1):
        if not 0 <= other < len(cues) or not _same_paragraph(cues[index], cues[other]):
            continue
        first, second = sorted((index, other))
        tokens = (cues[first].text + " " + cues[second].text).split()
        duration = cues[second].end - cues[first].start
        if _two_lines(tokens) is None or duration > MAX_CUE_SECONDS:
            continue
        joined = Cue(cues[first].start, cues[second].end, _lines(tokens), cues[first].paragraph)
        other_length = cues[other].end - cues[other].start
        options.append((other_length, first, joined))
    if not options:
        return None
    _, first, joined = min(options, key=lambda option: option[0])
    return first, joined


_EPSILON = 1e-9
