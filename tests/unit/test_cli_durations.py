import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from vizsync.cli import app

runner = CliRunner()
EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
TIMING = EXAMPLES / "timing.example.json"
CHART_MAP = EXAMPLES / "chart-map.yaml"
EXPECTED = (EXAMPLES / "chart-timing.example.yaml").read_text(encoding="utf-8")


def edited_timing(tmp_path: Path, change: Callable[[dict[str, Any]], None]) -> Path:
    """A copy of the example timing file, changed by ``change``."""
    data = json.loads(TIMING.read_text(encoding="utf-8"))
    change(data)
    path = tmp_path / "timing.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def durations(*arguments: str | Path):
    return runner.invoke(app, ["durations", *map(str, arguments)])


def test_the_yaml_is_printed_when_there_is_no_output_file() -> None:
    result = durations(TIMING, "--map", CHART_MAP)
    assert result.exit_code == 0
    assert result.stdout == EXPECTED


def test_the_yaml_is_written_to_the_output_file(
    tmp_path: Path, plain: Callable[[str], str]
) -> None:
    target = tmp_path / "chart-timing.yaml"
    result = durations(TIMING, "--map", CHART_MAP, "-o", target)
    assert result.exit_code == 0
    assert target.read_text(encoding="utf-8") == EXPECTED
    assert plain(result.stdout).startswith("Written: ")
    assert str(target) in plain(result.stdout)


def test_pad_lengthens_single_clips_and_the_last_clip_of_a_sequence() -> None:
    result = durations(TIMING, "--map", CHART_MAP, "--pad", "0.5")
    assert result.exit_code == 0
    assert "    start: 10.6\n    duration: 11.0\n" in result.stdout
    assert "      - { n: 3, start: 89.5, duration: 12.0 }" in result.stdout


def test_a_negative_pad_is_a_usage_error() -> None:
    result = durations(TIMING, "--map", CHART_MAP, "--pad", "-1")
    assert result.exit_code == 1


def test_the_map_option_is_required() -> None:
    assert durations(TIMING).exit_code == 1


def test_warnings_go_to_standard_error_and_the_yaml_is_still_written(
    tmp_path: Path, plain: Callable[[str], str]
) -> None:
    short_map = tmp_path / "map.yaml"
    short_map.write_text("version: 1\ncharts:\n  tiny:\n    paragraphs: [P1]\n", encoding="utf-8")
    timing = edited_timing(tmp_path, lambda data: data["paragraphs"][0].update(end=1.4))
    result = durations(timing, "--map", short_map)
    assert result.exit_code == 0
    assert "warning: tiny: the clip is only 1.0 s long" in plain(result.stderr)
    assert "tiny:" in result.stdout


def test_a_missing_timing_file(tmp_path: Path, plain: Callable[[str], str]) -> None:
    result = durations(tmp_path / "nope.json", "--map", CHART_MAP)
    assert result.exit_code == 1
    assert "Cannot read the timing file" in plain(result.stderr)


def test_a_missing_chart_map(tmp_path: Path, plain: Callable[[str], str]) -> None:
    result = durations(TIMING, "--map", tmp_path / "nope.yaml")
    assert result.exit_code == 1
    assert "Cannot read the chart map" in plain(result.stderr)


def test_a_bad_chart_map_lists_every_problem_and_writes_nothing(
    tmp_path: Path, plain: Callable[[str], str]
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 1\ncharts:\n  Bad:\n    paragraphs: [P1]\n  ok:\n    paragraphs: []\n",
        encoding="utf-8",
    )
    target = tmp_path / "out.yaml"
    result = durations(TIMING, "--map", bad, "-o", target)
    assert result.exit_code == 1
    err = plain(result.stderr)
    assert "charts.Bad" in err and "charts.ok.paragraphs" in err
    assert not target.exists()


def test_a_paragraph_that_is_not_in_the_timing_file_is_an_error(
    tmp_path: Path, plain: Callable[[str], str]
) -> None:
    bad = tmp_path / "map.yaml"
    bad.write_text("version: 1\ncharts:\n  a:\n    paragraphs: [P2, P99]\n", encoding="utf-8")
    result = durations(TIMING, "--map", bad)
    assert result.exit_code == 1
    assert "charts.a: P99 is not in the timing file" in plain(result.stderr)


def test_a_missing_paragraph_is_an_error(tmp_path: Path, plain: Callable[[str], str]) -> None:
    timing = edited_timing(
        tmp_path,
        lambda data: data["paragraphs"][1].update(
            start=None, end=None, duration=None, confidence=0.0, status="missing"
        ),
    )
    result = durations(timing, "--map", CHART_MAP)
    assert result.exit_code == 1
    assert "P2 was not found in the audio" in plain(result.stderr)


def test_a_file_that_is_not_a_timing_file(tmp_path: Path, plain: Callable[[str], str]) -> None:
    other = tmp_path / "other.json"
    other.write_text("{}", encoding="utf-8")
    result = durations(other, "--map", CHART_MAP)
    assert result.exit_code == 1
    assert "not a vizsync timing file" in plain(result.stderr)


def test_the_help_lists_the_command(plain: Callable[[str], str]) -> None:
    result = runner.invoke(app, ["--help"])
    assert "durations" in plain(result.stdout)


@pytest.mark.parametrize("option", ["--map", "--pad", "-o"])
def test_the_options_are_documented(option: str, plain: Callable[[str], str]) -> None:
    result = runner.invoke(app, ["durations", "--help"])
    assert option in plain(result.stdout)
