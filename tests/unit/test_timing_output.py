import csv
import json
from pathlib import Path

import pytest

from vizsync.audio.inputs import AudioMode
from vizsync.audio.timeline import Part
from vizsync.errors import OutputError
from vizsync.match.spans import ParagraphStatus
from vizsync.output.table import write_timing_csv
from vizsync.output.timing import build_timing, write_timing_json
from vizsync.pipeline import AlignmentResult, ChapterResult, ParagraphResult


def sample_result() -> AlignmentResult:
    return AlignmentResult(
        script_name="northwind.md",
        mode=AudioMode.PARTS,
        offset=0.0,
        total_duration=71.4,
        parts=[Part(Path("C:/audio/part1.wav"), 0.0, 38.2), Part(Path("part2.wav"), 38.2, 33.2)],
        chapters=[
            ChapterResult("The Hook", "P1", "P2", 0.4123, 21.1),
            ChapterResult("Yükseliş, the rise", "P3", "P3", None, None),
        ],
        paragraphs=[
            ParagraphResult("P1", "The Hook", 0.4123, 9.8, 0.98123, ParagraphStatus.OK),
            ParagraphResult("P2", "The Hook", 10.6, 21.1, 0.62, ParagraphStatus.LOW_CONFIDENCE),
            ParagraphResult("P3", "Yükseliş, the rise", None, None, 0.0, ParagraphStatus.MISSING),
        ],
        warnings=["P2: low confidence (0.62). The narration may differ from the script."],
        transcription_seconds=1.0,
        matching_seconds=0.1,
    )


# --- timing.json -------------------------------------------------------------------------------


def test_json_follows_the_spec_layout(tmp_path: Path) -> None:
    path = tmp_path / "timing.json"
    write_timing_json(build_timing(sample_result(), tool="vizsync 0.1.0"), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert list(data) == [
        "version", "tool", "script", "mode", "offset", "total_duration",
        "audio", "chapters", "paragraphs", "warnings",
    ]  # fmt: skip
    assert data["version"] == 1
    assert data["tool"] == "vizsync 0.1.0"
    assert data["script"] == "northwind.md"
    assert data["mode"] == "parts"
    assert data["offset"] == 0.0
    assert data["total_duration"] == 71.4
    assert data["warnings"] == [
        "P2: low confidence (0.62). The narration may differ from the script."
    ]


def test_audio_entries_use_file_names(tmp_path: Path) -> None:
    timing = build_timing(sample_result(), tool="t")
    assert [a.model_dump() for a in timing.audio] == [
        {"file": "part1.wav", "offset": 0.0, "duration": 38.2},
        {"file": "part2.wav", "offset": 38.2, "duration": 33.2},
    ]


def test_chapter_entries(tmp_path: Path) -> None:
    path = tmp_path / "timing.json"
    write_timing_json(build_timing(sample_result(), tool="t"), path)
    chapters = json.loads(path.read_text(encoding="utf-8"))["chapters"]
    assert list(chapters[0]) == ["title", "start", "end", "first", "last"]
    assert chapters[0] == {
        "title": "The Hook",
        "start": 0.412,
        "end": 21.1,
        "first": "P1",
        "last": "P2",
    }
    assert chapters[1]["start"] is None and chapters[1]["end"] is None


def test_paragraph_entries_round_to_milliseconds_and_use_null_for_missing(tmp_path: Path) -> None:
    path = tmp_path / "timing.json"
    write_timing_json(build_timing(sample_result(), tool="t"), path)
    paragraphs = json.loads(path.read_text(encoding="utf-8"))["paragraphs"]
    assert list(paragraphs[0]) == [
        "id", "chapter", "start", "end", "duration", "confidence", "status"
    ]  # fmt: skip
    assert paragraphs[0] == {
        "id": "P1", "chapter": "The Hook", "start": 0.412, "end": 9.8,
        "duration": 9.388, "confidence": 0.981, "status": "ok",
    }  # fmt: skip
    assert paragraphs[1]["status"] == "low_confidence"
    assert paragraphs[2] == {
        "id": "P3", "chapter": "Yükseliş, the rise", "start": None, "end": None,
        "duration": None, "confidence": 0.0, "status": "missing",
    }  # fmt: skip


def test_json_is_utf8_without_escapes_and_ends_with_a_newline(tmp_path: Path) -> None:
    path = tmp_path / "timing.json"
    write_timing_json(build_timing(sample_result(), tool="t"), path)
    raw = path.read_bytes()
    assert "Yükseliş".encode() in raw
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")
    assert b"\r\n" not in raw


def test_json_write_failure_is_an_output_error(tmp_path: Path) -> None:
    with pytest.raises(OutputError) as info:
        write_timing_json(build_timing(sample_result(), tool="t"), tmp_path)
    assert str(tmp_path) in str(info.value)


# --- timing.csv ----------------------------------------------------------------------------------


def test_csv_has_a_byte_order_mark_and_the_spec_header(tmp_path: Path) -> None:
    path = tmp_path / "timing.csv"
    write_timing_csv(build_timing(sample_result(), tool="t"), path)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.reader(file))
    assert rows[0] == ["id", "chapter", "start", "end", "duration", "confidence", "status"]
    assert len(rows) == 4


def test_csv_rows_use_empty_cells_for_missing_and_quote_commas(tmp_path: Path) -> None:
    path = tmp_path / "timing.csv"
    write_timing_csv(build_timing(sample_result(), tool="t"), path)
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.reader(file))
    assert rows[1] == ["P1", "The Hook", "0.412", "9.8", "9.388", "0.981", "ok"]
    assert rows[2][-1] == "low_confidence"
    assert rows[3] == ["P3", "Yükseliş, the rise", "", "", "", "0.0", "missing"]


def test_csv_write_failure_is_an_output_error(tmp_path: Path) -> None:
    with pytest.raises(OutputError):
        write_timing_csv(build_timing(sample_result(), tool="t"), tmp_path)
