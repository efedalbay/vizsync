from pathlib import Path

import pytest

from vizsync.errors import ChartMapError
from vizsync.integrations.chartmap import ChartEntry, load_chart_map, parse_chart_map

SOURCE = Path("chart-map.yaml")


def parse(text: str):
    return parse_chart_map(text, source=SOURCE)


def problems(text: str) -> list[str]:
    with pytest.raises(ChartMapError) as caught:
        parse(text)
    return str(caught.value).splitlines()


VALID = """\
version: 1
charts:
  peak-valuation:
    paragraphs: [P2]
  valuation:
    paragraphs: [P3, P4]
  collapse:
    sequence: true
    paragraphs: [P6, P7, P8]
"""


def test_a_valid_map_keeps_the_order_of_the_file() -> None:
    result = parse(VALID)
    assert result.charts == [
        ChartEntry(id="peak-valuation", paragraphs=["P2"], sequence=False),
        ChartEntry(id="valuation", paragraphs=["P3", "P4"], sequence=False),
        ChartEntry(id="collapse", paragraphs=["P6", "P7", "P8"], sequence=True),
    ]


def test_the_shipped_example_is_valid() -> None:
    example = Path(__file__).resolve().parents[2] / "examples" / "chart-map.yaml"
    assert [chart.id for chart in load_chart_map(example).charts] == [
        "peak-valuation",
        "valuation",
        "collapse",
    ]


def test_a_missing_file_is_an_error_naming_it(tmp_path: Path) -> None:
    with pytest.raises(ChartMapError, match="Cannot read the chart map"):
        load_chart_map(tmp_path / "nope.yaml")


def test_text_that_is_not_yaml_is_an_error() -> None:
    assert "chart-map.yaml: not valid YAML" in problems("charts: [unclosed")[0]


def test_the_top_level_must_be_a_mapping() -> None:
    assert problems("- a\n- b\n") == ["chart-map.yaml: the file must hold 'version' and 'charts'"]


def test_the_version_is_required_and_must_be_1() -> None:
    assert problems("charts:\n  a:\n    paragraphs: [P1]\n") == [
        "chart-map.yaml: version is required (write 'version: 1')"
    ]
    assert problems("version: 2\ncharts:\n  a:\n    paragraphs: [P1]\n") == [
        "chart-map.yaml: version must be 1, got 2"
    ]


def test_at_least_one_chart_is_required() -> None:
    assert problems("version: 1\n") == ["chart-map.yaml: charts: at least one chart is required"]
    assert problems("version: 1\ncharts: {}\n") == [
        "chart-map.yaml: charts: at least one chart is required"
    ]


@pytest.mark.parametrize("name", ["Peak_Valuation", "peak valuation", "peak.valuation", "é"])
def test_a_chart_id_may_only_use_lowercase_letters_digits_and_hyphens(name: str) -> None:
    text = f'version: 1\ncharts:\n  "{name}":\n    paragraphs: [P1]\n'
    assert problems(text) == [
        f"chart-map.yaml: charts.{name}: the id may only use a-z, 0-9 and '-'"
    ]


@pytest.mark.parametrize("name", ["con", "nul", "com1", "lpt9"])
def test_names_windows_reserves_are_not_chart_ids(name: str) -> None:
    text = f"version: 1\ncharts:\n  {name}:\n    paragraphs: [P1]\n"
    assert problems(text) == [f"chart-map.yaml: charts.{name}: '{name}' is a name Windows reserves"]


def test_paragraphs_are_required_and_must_be_a_list_of_names() -> None:
    assert problems("version: 1\ncharts:\n  a: {}\n") == [
        "chart-map.yaml: charts.a: paragraphs is required"
    ]
    for value in ("[]", "P1", "[1, 2]", "[P1, [P2]]"):
        text = f"version: 1\ncharts:\n  a:\n    paragraphs: {value}\n"
        assert problems(text) == [
            "chart-map.yaml: charts.a.paragraphs: must be a list of paragraph identifiers"
        ]


def test_an_entry_must_be_a_mapping() -> None:
    assert problems("version: 1\ncharts:\n  a: [P1]\n") == [
        "chart-map.yaml: charts.a: must have 'paragraphs' (and optionally 'sequence')"
    ]


def test_unknown_fields_are_rejected() -> None:
    text = "version: 1\ncharts:\n  a:\n    paragraphs: [P1]\n    colour: red\n"
    assert problems(text) == [
        "chart-map.yaml: charts.a: unknown field 'colour' (use paragraphs, sequence)"
    ]


def test_sequence_must_be_true_or_false() -> None:
    text = "version: 1\ncharts:\n  a:\n    paragraphs: [P1, P2]\n    sequence: yes please\n"
    assert problems(text) == ["chart-map.yaml: charts.a.sequence: must be true or false"]


@pytest.mark.parametrize("count", [1, 9])
def test_a_sequence_needs_two_to_eight_paragraphs(count: int) -> None:
    names = ", ".join(f"P{n}" for n in range(1, count + 1))
    text = f"version: 1\ncharts:\n  a:\n    sequence: true\n    paragraphs: [{names}]\n"
    assert problems(text) == [
        f"chart-map.yaml: charts.a: a sequence needs 2 to 8 paragraphs, got {count}"
    ]


def test_two_and_eight_paragraphs_are_fine_for_a_sequence() -> None:
    for count in (2, 8):
        names = ", ".join(f"P{n}" for n in range(1, count + 1))
        text = f"version: 1\ncharts:\n  a:\n    sequence: true\n    paragraphs: [{names}]\n"
        assert len(parse(text).charts[0].paragraphs) == count


def test_a_paragraph_listed_twice_in_one_chart_is_an_error() -> None:
    text = "version: 1\ncharts:\n  a:\n    paragraphs: [P1, P2, P1]\n"
    assert problems(text) == ["chart-map.yaml: charts.a: P1 is listed twice"]


def test_every_problem_is_reported_together() -> None:
    text = "version: 3\ncharts:\n  Bad:\n    paragraphs: [P1]\n  b:\n    paragraphs: []\n"
    assert len(problems(text)) == 3


# --- Chart tags in the script ---------------------------------------------------------------------

from vizsync.integrations.chartmap import (  # noqa: E402
    ChartMap,
    chart_map_from_script,
    merge_chart_maps,
)
from vizsync.script.models import TextMode  # noqa: E402
from vizsync.script.parser import load_script, parse_script  # noqa: E402

SCRIPT_FILE = Path("senaryo.md")


def script_with(*lines: str):
    """A script of four paragraphs; ``lines`` is placed after the first line of each paragraph."""
    text = ""
    for number in range(1, 5):
        text += f"P{number} — Text {number}.\n"
        for line in lines:
            if line.startswith(f"{number}:"):
                text += line.split(":", 1)[1] + "\n"
        text += "\n"
    return parse_script(text, TextMode.INLINE)


def script_problems(*lines: str) -> list[str]:
    with pytest.raises(ChartMapError) as caught:
        chart_map_from_script(script_with(*lines), source=SCRIPT_FILE)
    return str(caught.value).splitlines()


def test_paragraphs_with_the_same_chart_tag_make_one_chart() -> None:
    script = script_with(
        "1:<!-- chart: bet-size -->",
        "2:<!-- chart: valuation -->",
        "3:<!-- chart: valuation -->",
    )
    result = chart_map_from_script(script, source=SCRIPT_FILE)
    assert result.charts == [
        ChartEntry("bet-size", ["P1"], False),
        ChartEntry("valuation", ["P2", "P3"], False),
    ]


def test_a_sequence_tag_on_every_paragraph_makes_a_sequence() -> None:
    script = script_with(
        "2:<!-- chart: collapse, sequence -->",
        "3:<!-- chart: collapse, sequence -->",
        "4:<!-- chart: collapse, sequence -->",
    )
    (chart,) = chart_map_from_script(script, source=SCRIPT_FILE).charts
    assert chart == ChartEntry("collapse", ["P2", "P3", "P4"], True)


def test_a_paragraph_in_two_charts_is_in_both() -> None:
    script = script_with("1:<!-- chart: a -->", "1:<!-- chart: b -->", "2:<!-- chart: b -->")
    assert chart_map_from_script(script, source=SCRIPT_FILE).charts == [
        ChartEntry("a", ["P1"], False),
        ChartEntry("b", ["P1", "P2"], False),
    ]


def test_a_script_without_tags_gives_an_empty_map() -> None:
    assert chart_map_from_script(script_with(), source=SCRIPT_FILE).charts == []


def test_sequence_on_only_some_paragraphs_of_a_chart_is_an_error_naming_the_line() -> None:
    message = "'sequence' must be on every paragraph of the chart or on none"
    assert script_problems(
        "2:<!-- chart: collapse, sequence -->", "3:<!-- chart: collapse -->"
    ) == [f"senaryo.md line 7: charts.collapse: {message}"]


def test_a_sequence_of_one_paragraph_is_an_error() -> None:
    assert script_problems("2:<!-- chart: collapse, sequence -->") == [
        "senaryo.md line 4: charts.collapse: a sequence needs 2 to 8 paragraphs, got 1"
    ]


def test_a_chart_id_windows_reserves_is_an_error() -> None:
    assert script_problems("1:<!-- chart: con -->") == [
        "senaryo.md line 2: charts.con: 'con' is a name Windows reserves"
    ]


def test_the_example_script_and_the_example_map_describe_the_same_charts() -> None:
    examples = Path(__file__).resolve().parents[2] / "examples"
    script = load_script(examples / "northwind-script.md", TextMode.QUOTE)
    from_script = chart_map_from_script(script, source=examples / "northwind-script.md")
    assert from_script.charts == load_chart_map(examples / "chart-map.yaml").charts


# --- Using the map file and the script together -------------------------------------------------


def test_two_maps_are_put_together_in_order() -> None:
    first = ChartMap([ChartEntry("a", ["P1"], False)])
    second = ChartMap([ChartEntry("b", ["P2"], False)])
    merged = merge_chart_maps(first, second, names=("map.yaml", "senaryo.md"))
    assert [chart.id for chart in merged.charts] == ["a", "b"]


def test_a_chart_in_both_maps_is_an_error_naming_both_sources() -> None:
    first = ChartMap([ChartEntry("a", ["P1"], False), ChartEntry("b", ["P2"], False)])
    second = ChartMap([ChartEntry("b", ["P3"], False), ChartEntry("a", ["P4"], False)])
    with pytest.raises(ChartMapError) as caught:
        merge_chart_maps(first, second, names=("map.yaml", "senaryo.md"))
    assert str(caught.value).splitlines() == [
        "charts.a is in both map.yaml and senaryo.md; give each chart in one place",
        "charts.b is in both map.yaml and senaryo.md; give each chart in one place",
    ]
