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
