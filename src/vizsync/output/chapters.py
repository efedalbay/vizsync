"""``chapters.txt``: the chapter list for a YouTube description.

One line per chapter, ``MM:SS Title`` (``H:MM:SS`` on every line when the video lasts an hour or
more). YouTube needs the first chapter at 00:00, at least three chapters, and at least 10 s
between chapter starts. Times are rounded down to whole seconds. Anything YouTube would ignore
the list for is reported as a warning rather than silently changed.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from vizsync.errors import OutputError
from vizsync.pipeline import ChapterResult

MIN_CHAPTERS = 3
MIN_CHAPTER_SECONDS = 10
FIRST_CHAPTER_TOLERANCE = 1.0
"""A first chapter starting later than this many seconds is reported."""


@dataclass(frozen=True)
class ChapterList:
    """The lines of ``chapters.txt`` and the warnings about them."""

    lines: list[str]
    warnings: list[str]


def build_chapters(chapters: Sequence[ChapterResult], *, video_end: float) -> ChapterList:
    """Build the chapter lines.

    Args:
        chapters: The chapters in script order, with the times of the found paragraphs.
        video_end: Where the video ends, in seconds; the last chapter runs until then.
    """
    warnings: list[str] = []
    found: list[tuple[str, float]] = []
    for chapter in chapters:
        if chapter.start is None:
            warnings.append(
                f"chapters: '{chapter.title}' skipped, none of its paragraphs was found."
            )
        else:
            found.append((chapter.title, chapter.start))
    if not found:
        warnings.append("chapters: no chapter was found, chapters.txt is not written.")
        return ChapterList([], warnings)

    first_title, first_start = found[0]
    if first_start > FIRST_CHAPTER_TOLERANCE:
        warnings.append(
            f"chapters: '{first_title}' starts at {_clock(first_start, hours=False)} but YouTube "
            "needs the first chapter at 00:00; it is written at 00:00."
        )
    seconds = [0] + [math.floor(start) for _, start in found[1:]]
    warnings += _length_warnings(found, seconds, video_end)
    if len(found) < MIN_CHAPTERS:
        noun = "chapter" if len(found) == 1 else "chapters"
        warnings.append(f"chapters: only {len(found)} {noun}, YouTube needs at least 3.")
    hours = video_end >= 3600
    lines = [
        f"{_clock(time, hours=hours)} {title}"
        for (title, _), time in zip(found, seconds, strict=True)
    ]
    return ChapterList(lines, warnings)


def write_chapters(chapter_list: ChapterList, path: Path) -> None:
    """Write ``chapters.txt`` as UTF-8 with a trailing newline.

    Raises:
        OutputError: If the file cannot be written.
    """
    try:
        with path.open("w", encoding="utf-8", newline="\n") as file:
            file.write("\n".join(chapter_list.lines) + "\n")
    except OSError as error:
        raise OutputError(f"Cannot write the file ({error.strerror})", path=path) from None


def _length_warnings(
    found: Sequence[tuple[str, float]], seconds: Sequence[int], video_end: float
) -> list[str]:
    ends = [*seconds[1:], math.floor(video_end)]
    return [
        f"chapters: '{title}' is only {end - begin} s long, YouTube needs at least "
        f"{MIN_CHAPTER_SECONDS} s."
        for (title, _), begin, end in zip(found, seconds, ends, strict=True)
        if end - begin < MIN_CHAPTER_SECONDS
    ]


def _clock(seconds: float, *, hours: bool) -> str:
    whole = math.floor(seconds)
    minutes_total, secs = divmod(whole, 60)
    if hours:
        hour, minutes = divmod(minutes_total, 60)
        return f"{hour}:{minutes:02d}:{secs:02d}"
    return f"{minutes_total:02d}:{secs:02d}"
