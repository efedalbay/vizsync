"""Decide which output files to write for an alignment, and write them.

``prepare_outputs`` runs first because the chapter list can add warnings, and warnings belong
in ``timing.json`` and on the console. ``write_outputs`` then writes everything in one go.
"""

from dataclasses import dataclass, replace
from pathlib import Path

from vizsync.errors import OutputError
from vizsync.output.chapters import ChapterList, build_chapters, write_chapters
from vizsync.output.edl import EdlSettings, build_edl, write_edl
from vizsync.output.table import write_timing_csv
from vizsync.output.timing import build_timing, write_timing_json
from vizsync.pipeline import AlignmentResult

FORMATS = ("json", "csv", "chapters", "edl")


@dataclass(frozen=True)
class Outputs:
    """The result (with the warnings of the chosen files added) and what to write."""

    result: AlignmentResult
    formats: list[str]
    chapters: ChapterList | None
    edl_text: str | None


def prepare_outputs(
    result: AlignmentResult, formats: list[str], edl: EdlSettings | None
) -> Outputs:
    """Build the chapter list and the marker file, and add the chapter warnings to the result."""
    chapters = None
    if "chapters" in formats:
        chapters = build_chapters(result.chapters, video_end=result.offset + result.total_duration)
        result = replace(result, warnings=[*result.warnings, *chapters.warnings])
    edl_text = None
    if "edl" in formats and edl is not None:
        markers = [(p.id, p.start) for p in result.paragraphs if p.start is not None]
        edl_text = build_edl(result.script_name, markers, edl)
    return Outputs(result, formats, chapters, edl_text)


def write_outputs(outputs: Outputs, out: Path, *, tool: str) -> list[Path]:
    """Write the chosen files into ``out`` (created if needed) and return their paths.

    Raises:
        OutputError: If the folder or a file cannot be written.
    """
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise OutputError(f"Cannot create the output folder ({error.strerror})", path=out) from None
    timing = build_timing(outputs.result, tool=tool)
    written: list[Path] = []
    if "json" in outputs.formats:
        write_timing_json(timing, out / "timing.json")
        written.append(out / "timing.json")
    if "csv" in outputs.formats:
        write_timing_csv(timing, out / "timing.csv")
        written.append(out / "timing.csv")
    if outputs.chapters is not None and outputs.chapters.lines:
        write_chapters(outputs.chapters, out / "chapters.txt")
        written.append(out / "chapters.txt")
    if outputs.edl_text is not None:
        write_edl(outputs.edl_text, out / "markers.edl")
        written.append(out / "markers.edl")
    return written
