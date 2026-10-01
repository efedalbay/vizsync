"""``timing.csv``: one row per paragraph, for a spreadsheet."""

import csv
from pathlib import Path

from vizsync.errors import OutputError
from vizsync.output.timing import Timing

HEADER = ["id", "chapter", "start", "end", "duration", "confidence", "status"]


def write_timing_csv(timing: Timing, path: Path) -> None:
    """Write ``timing.csv`` as UTF-8 with a byte order mark, so Excel on Windows reads it right.

    Missing times are empty cells.

    Raises:
        OutputError: If the file cannot be written.
    """
    try:
        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(HEADER)
            for paragraph in timing.paragraphs:
                writer.writerow(
                    [
                        paragraph.id,
                        paragraph.chapter,
                        _cell(paragraph.start),
                        _cell(paragraph.end),
                        _cell(paragraph.duration),
                        _cell(paragraph.confidence),
                        paragraph.status,
                    ]
                )
    except OSError as error:
        raise OutputError(f"Cannot write the file ({error.strerror})", path=path) from None


def _cell(value: float | None) -> str:
    return "" if value is None else str(value)
