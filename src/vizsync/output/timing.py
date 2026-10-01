"""``timing.json``: the full result, and the source of truth for the other output files."""

import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

from vizsync.errors import OutputError, TimingFileError
from vizsync.pipeline import AlignmentResult

TIMING_VERSION = 1


class AudioEntry(BaseModel):
    """One audio file on the timeline."""

    file: str
    offset: float
    duration: float


class ChapterEntry(BaseModel):
    """A chapter; ``start`` and ``end`` are None when all its paragraphs are missing."""

    title: str
    start: float | None
    end: float | None
    first: str
    last: str


class ParagraphEntry(BaseModel):
    """A paragraph; ``start``, ``end`` and ``duration`` are None when it is missing."""

    id: str
    chapter: str
    start: float | None
    end: float | None
    duration: float | None
    confidence: float
    status: str


class Timing(BaseModel):
    """The contents of ``timing.json`` (see docs/SPEC.md section 5)."""

    version: int
    tool: str
    script: str
    mode: str
    offset: float
    total_duration: float
    audio: list[AudioEntry]
    chapters: list[ChapterEntry]
    paragraphs: list[ParagraphEntry]
    warnings: list[str]


def build_timing(result: AlignmentResult, *, tool: str) -> Timing:
    """Turn an alignment result into the ``timing.json`` model. Times are rounded to the ms."""
    return Timing(
        version=TIMING_VERSION,
        tool=tool,
        script=result.script_name,
        mode=result.mode.value,
        offset=_ms(result.offset),
        total_duration=_ms(result.total_duration),
        audio=[
            AudioEntry(file=part.file.name, offset=_ms(part.offset), duration=_ms(part.duration))
            for part in result.parts
        ],
        chapters=[
            ChapterEntry(
                title=chapter.title,
                start=_ms(chapter.start),
                end=_ms(chapter.end),
                first=chapter.first,
                last=chapter.last,
            )
            for chapter in result.chapters
        ],
        paragraphs=[
            ParagraphEntry(
                id=paragraph.id,
                chapter=paragraph.chapter,
                start=_ms(paragraph.start),
                end=_ms(paragraph.end),
                duration=_duration(paragraph.start, paragraph.end),
                confidence=_ms(paragraph.confidence),
                status=paragraph.status.value,
            )
            for paragraph in result.paragraphs
        ],
        warnings=list(result.warnings),
    )


def write_timing_json(timing: Timing, path: Path) -> None:
    """Write ``timing.json`` as UTF-8 with a trailing newline.

    Raises:
        OutputError: If the file cannot be written.
    """
    text = timing.model_dump_json(indent=2) + "\n"
    try:
        with path.open("w", encoding="utf-8", newline="\n") as file:
            file.write(text)
    except OSError as error:
        raise OutputError(f"Cannot write the file ({error.strerror})", path=path) from None


def read_timing_json(path: Path) -> Timing:
    """Read a ``timing.json`` written by vizsync.

    Raises:
        TimingFileError: If the file cannot be read, is not JSON, is not a vizsync result, or has
            another version.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise TimingFileError(
            f"Cannot read the timing file ({error.strerror})", path=path
        ) from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TimingFileError("The timing file is not valid JSON", path=path) from None
    try:
        timing = Timing.model_validate(data)
    except ValidationError:
        raise TimingFileError(
            "This is not a vizsync timing file (run 'vizsync align' to make one)", path=path
        ) from None
    if timing.version != TIMING_VERSION:
        raise TimingFileError(
            f"The timing file has version {timing.version}; this vizsync reads version "
            f"{TIMING_VERSION}",
            path=path,
        )
    return timing


def _ms(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def _duration(start: float | None, end: float | None) -> float | None:
    return None if start is None or end is None else round(end - start, 3)
