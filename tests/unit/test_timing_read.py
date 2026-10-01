import json
from pathlib import Path

import pytest

from vizsync.errors import TimingFileError
from vizsync.output.timing import TIMING_VERSION, read_timing_json

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "timing.example.json"


def test_the_shipped_example_is_read() -> None:
    timing = read_timing_json(EXAMPLE)
    assert timing.version == TIMING_VERSION
    assert [p.id for p in timing.paragraphs] == [f"P{n}" for n in range(1, 9)]
    assert timing.paragraphs[1].start == 10.6


def test_a_missing_file_is_an_error_naming_it(tmp_path: Path) -> None:
    with pytest.raises(TimingFileError, match="Cannot read the timing file") as caught:
        read_timing_json(tmp_path / "timing.json")
    assert caught.value.path == tmp_path / "timing.json"


def test_text_that_is_not_json_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "timing.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(TimingFileError, match="not valid JSON"):
        read_timing_json(path)


def test_json_that_is_not_a_timing_file_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "timing.json"
    path.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
    with pytest.raises(TimingFileError, match="not a vizsync timing file"):
        read_timing_json(path)


def test_another_version_is_an_error(tmp_path: Path) -> None:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["version"] = 2
    path = tmp_path / "timing.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(TimingFileError, match="version 2"):
        read_timing_json(path)


def test_a_file_with_a_byte_order_mark_is_read(tmp_path: Path) -> None:
    path = tmp_path / "timing.json"
    path.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8-sig")
    assert read_timing_json(path).script == "northwind-script.md"
