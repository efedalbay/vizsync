from pathlib import Path

import pytest

from vizsync.errors import ChartMapError
from vizsync.integrations.chartmap import ChartEntry, ChartMap, load_chart_map
from vizsync.integrations.vizreel import (
    Clip,
    compute_chart_timing,
    format_chart_timing,
    write_chart_timing,
)
from vizsync.output.timing import ParagraphEntry, Timing, read_timing_json

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def timing_of(*rows: tuple[str, float | None, float | None]) -> Timing:
    """A timing with the given ``(id, start, end)`` paragraphs; ``None`` times mean missing."""
    return Timing(
        version=1,
        tool="test",
        script="s.md",
        mode="parts",
        offset=0.0,
        total_duration=200.0,
        audio=[],
        chapters=[],
        paragraphs=[
            ParagraphEntry(
                id=name,
                chapter="c",
                start=start,
                end=end,
                duration=None if start is None or end is None else round(end - start, 3),
                confidence=0.0 if start is None else 1.0,
                status="missing" if start is None else "ok",
            )
            for name, start, end in rows
        ],
        warnings=[],
    )


def chart(name: str, *paragraphs: str, sequence: bool = False) -> ChartMap:
    return ChartMap([ChartEntry(id=name, paragraphs=list(paragraphs), sequence=sequence)])


TIMING = timing_of(
    ("P1", 0.4, 9.8),
    ("P2", 10.6, 21.1),
    ("P3", 21.9, 38.0),
    ("P4", 38.9, 49.5),
    ("P5", 50.3, 61.2),
)


# --- Single clips ------------------------------------------------------------------------


def test_a_single_paragraph_starts_where_it_starts_and_lasts_until_it_ends() -> None:
    result = compute_chart_timing(TIMING, chart("a", "P2"))
    (a,) = result.charts
    assert (a.id, a.start, a.duration) == ("a", 10.6, 10.5)
    assert a.step_duration is None and a.clips == []
    assert result.warnings == []


def test_several_paragraphs_make_one_clip_over_the_silence_between_them() -> None:
    (a,) = compute_chart_timing(TIMING, chart("a", "P3", "P4")).charts
    assert (a.start, a.duration) == (21.9, 27.6)


def test_pad_is_added_to_the_end_of_a_clip() -> None:
    (a,) = compute_chart_timing(TIMING, chart("a", "P2"), pad=0.5).charts
    assert (a.start, a.duration) == (10.6, 11.0)


# --- Sequences ---------------------------------------------------------------------------


def test_sequence_clips_are_cut_back_to_back() -> None:
    (a,) = compute_chart_timing(TIMING, chart("a", "P3", "P4", "P5", sequence=True)).charts
    assert a.clips == [Clip(1, 21.9, 17.0), Clip(2, 38.9, 11.4), Clip(3, 50.3, 10.9)]
    assert (a.start, a.duration, a.step_duration) == (21.9, 17.0, 11.4)


def test_the_last_clip_of_a_sequence_gets_the_pad() -> None:
    (a,) = compute_chart_timing(TIMING, chart("a", "P3", "P4", "P5", sequence=True), pad=1.0).charts
    assert a.clips[-1] == Clip(3, 50.3, 11.9)
    assert a.clips[0].duration == 17.0
    assert a.step_duration == 11.9


def test_step_duration_is_the_longest_later_clip() -> None:
    timing = timing_of(("P1", 0.0, 4.0), ("P2", 5.0, 9.0), ("P3", 20.0, 25.0), ("P4", 26.0, 28.0))
    (a,) = compute_chart_timing(timing, chart("a", "P1", "P2", "P3", "P4", sequence=True)).charts
    assert [clip.duration for clip in a.clips] == [5.0, 15.0, 6.0, 2.0]
    assert a.duration == 5.0
    assert a.step_duration == 15.0


def test_a_two_paragraph_sequence_has_one_later_clip() -> None:
    (a,) = compute_chart_timing(TIMING, chart("a", "P1", "P2", sequence=True)).charts
    assert a.clips == [Clip(1, 0.4, 10.2), Clip(2, 10.6, 10.5)]
    assert a.step_duration == 10.5


def test_numbers_are_rounded_to_milliseconds() -> None:
    timing = timing_of(("P1", 0.1, 0.2), ("P2", 10.3, 20.7))
    (a,) = compute_chart_timing(timing, chart("a", "P1", "P2", sequence=True)).charts
    assert a.clips[0].duration == 10.2
    assert a.clips[1].duration == 10.4


# --- Problems that stop the run ------------------------------------------------------------


def problems(timing: Timing, chart_map: ChartMap) -> list[str]:
    with pytest.raises(ChartMapError) as caught:
        compute_chart_timing(timing, chart_map)
    return str(caught.value).splitlines()


def test_an_unknown_paragraph_is_an_error() -> None:
    assert problems(TIMING, chart("a", "P2", "P9")) == [
        "charts.a: P9 is not in the timing file (it has P1 to P5)"
    ]


def test_a_missing_paragraph_is_an_error() -> None:
    timing = timing_of(("P1", 0.0, 4.0), ("P2", None, None), ("P3", 9.0, 12.0))
    assert problems(timing, chart("a", "P2", "P3")) == [
        "charts.a: P2 was not found in the audio, so it has no time"
    ]


def test_paragraphs_must_be_consecutive_and_in_script_order() -> None:
    expected = "charts.a: the paragraphs must be consecutive and in script order, got "
    assert problems(TIMING, chart("a", "P1", "P3")) == [expected + "P1, P3"]
    assert problems(TIMING, chart("a", "P4", "P3")) == [expected + "P4, P3"]


def test_every_problem_in_every_chart_is_reported() -> None:
    chart_map = ChartMap(
        [
            ChartEntry("a", ["P9"], False),
            ChartEntry("b", ["P1", "P3"], False),
            ChartEntry("c", ["P2"], False),
        ]
    )
    assert len(problems(TIMING, chart_map)) == 2


# --- Warnings ------------------------------------------------------------------------------


def test_a_clip_shorter_than_two_seconds_gives_a_warning() -> None:
    timing = timing_of(("P1", 0.0, 1.5))
    result = compute_chart_timing(timing, chart("a", "P1"))
    assert result.warnings == ["a: the clip is only 1.5 s long, vizreel needs at least 2 s."]


def test_exactly_two_seconds_is_long_enough() -> None:
    assert compute_chart_timing(timing_of(("P1", 0.0, 2.0)), chart("a", "P1")).warnings == []


def test_a_short_sequence_clip_names_its_number() -> None:
    timing = timing_of(("P1", 0.0, 6.0), ("P2", 6.5, 7.0), ("P3", 7.2, 15.0))
    result = compute_chart_timing(timing, chart("a", "P1", "P2", "P3", sequence=True))
    assert "a: clip 2 is only 0.7 s long, vizreel needs at least 2 s." in result.warnings


def test_a_later_clip_much_shorter_than_step_duration_gives_a_warning() -> None:
    timing = timing_of(("P1", 0.0, 5.0), ("P2", 6.0, 20.0), ("P3", 20.0, 24.0))
    result = compute_chart_timing(timing, chart("a", "P1", "P2", "P3", sequence=True))
    assert result.warnings == [
        "a: clip 3 (4.0 s) is much shorter than step_duration (14.0 s); trim it in the editor."
    ]


def test_a_later_clip_of_half_the_step_duration_is_not_much_shorter() -> None:
    timing = timing_of(("P1", 0.0, 5.0), ("P2", 6.0, 20.0), ("P3", 20.0, 27.0))
    assert compute_chart_timing(timing, chart("a", "P1", "P2", "P3", sequence=True)).warnings == []


def test_a_low_confidence_paragraph_gives_a_warning() -> None:
    timing = TIMING.model_copy(deep=True)
    timing.paragraphs[1].status = "low_confidence"
    timing.paragraphs[1].confidence = 0.62
    result = compute_chart_timing(timing, chart("a", "P2"))
    assert result.warnings == ["a: P2 has low confidence (0.62), its time may be off."]


# --- Text and file -------------------------------------------------------------------------


def test_the_text_lists_single_clips_and_sequences() -> None:
    chart_map = ChartMap(
        [
            ChartEntry("peak-valuation", ["P2"], False),
            ChartEntry("collapse", ["P3", "P4", "P5"], True),
        ]
    )
    text = format_chart_timing(compute_chart_timing(TIMING, chart_map))
    assert text == (
        "charts:\n"
        "  peak-valuation:\n"
        "    start: 10.6\n"
        "    duration: 10.5\n"
        "  collapse:\n"
        "    start: 21.9\n"
        "    duration: 17.0\n"
        "    step_duration: 11.4\n"
        "    clips:\n"
        "      - { n: 1, start: 21.9, duration: 17.0 }\n"
        "      - { n: 2, start: 38.9, duration: 11.4 }\n"
        "      - { n: 3, start: 50.3, duration: 10.9 }\n"
    )


def test_numbers_keep_at_least_one_decimal_and_drop_trailing_zeros() -> None:
    timing = timing_of(("P1", 3.0, 8.25))
    text = format_chart_timing(compute_chart_timing(timing, chart("a", "P1")))
    assert "    start: 3.0\n    duration: 5.25\n" in text


def test_the_file_is_utf8_with_unix_line_endings(tmp_path: Path) -> None:
    path = tmp_path / "chart-timing.yaml"
    write_chart_timing("charts:\n", path)
    assert path.read_bytes() == b"charts:\n"


def test_an_unwritable_file_is_an_error(tmp_path: Path) -> None:
    from vizsync.errors import OutputError

    with pytest.raises(OutputError, match="Cannot write"):
        write_chart_timing("x", tmp_path)


# --- The shipped example, against a hand calculation ----------------------------------------


def test_the_example_map_and_timing_give_the_hand_calculated_numbers() -> None:
    timing = read_timing_json(EXAMPLES / "timing.example.json")
    chart_map = load_chart_map(EXAMPLES / "chart-map.yaml")
    result = compute_chart_timing(timing, chart_map)
    by_id = {c.id: c for c in result.charts}
    # peak-valuation = P2: 10.6 to 21.1
    assert (by_id["peak-valuation"].start, by_id["peak-valuation"].duration) == (10.6, 10.5)
    # valuation = P3 and P4: 21.9 to 49.5
    assert (by_id["valuation"].start, by_id["valuation"].duration) == (21.9, 27.6)
    # collapse = P6, P7, P8 as a sequence: 62.0 | 76.1 | 89.5 and the end of P8 at 101.0
    collapse = by_id["collapse"]
    assert collapse.clips == [Clip(1, 62.0, 14.1), Clip(2, 76.1, 13.4), Clip(3, 89.5, 11.5)]
    assert (collapse.start, collapse.duration, collapse.step_duration) == (62.0, 14.1, 13.4)
    assert result.warnings == []


def test_the_example_text_matches_the_shipped_file() -> None:
    timing = read_timing_json(EXAMPLES / "timing.example.json")
    chart_map = load_chart_map(EXAMPLES / "chart-map.yaml")
    text = format_chart_timing(compute_chart_timing(timing, chart_map))
    assert text == (EXAMPLES / "chart-timing.example.yaml").read_text(encoding="utf-8")
