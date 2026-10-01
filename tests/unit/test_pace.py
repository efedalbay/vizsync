from vizsync.match.pace import Pace, slow_paragraphs


def paces(*rows: tuple[str, int, float]) -> list[Pace]:
    return [Pace(id=name, words=words, seconds=seconds) for name, words, seconds in rows]


def test_a_paragraph_much_slower_than_the_rest_is_reported() -> None:
    rows = paces(("P1", 10, 4.0), ("P2", 10, 4.2), ("P3", 10, 4.1), ("P4", 12, 730.0))
    assert slow_paragraphs(rows) == ["P4"]


def test_several_slow_paragraphs_are_reported_in_order() -> None:
    rows = paces(("P1", 9, 42.0), ("P2", 5, 2.0), ("P3", 6, 2.4), ("P4", 12, 730.0), ("P5", 7, 3.0))
    assert slow_paragraphs(rows) == ["P1", "P4"]


def test_an_evenly_paced_narration_has_no_slow_paragraph() -> None:
    rows = paces(("P1", 10, 4.0), ("P2", 8, 3.5), ("P3", 12, 5.0), ("P4", 9, 3.6))
    assert slow_paragraphs(rows) == []


def test_a_slow_narrator_is_not_flagged_because_the_median_is_the_reference() -> None:
    rows = paces(("P1", 10, 10.0), ("P2", 10, 11.0), ("P3", 10, 12.0), ("P4", 10, 10.5))
    assert slow_paragraphs(rows) == []


def test_a_short_paragraph_is_never_flagged_whatever_its_pace() -> None:
    rows = paces(("P1", 10, 4.0), ("P2", 10, 4.0), ("P3", 10, 4.0), ("P4", 1, 4.5))
    assert slow_paragraphs(rows) == []


def test_exactly_three_times_the_median_pace_is_not_flagged() -> None:
    rows = paces(("P1", 10, 4.0), ("P2", 10, 4.0), ("P3", 10, 4.0), ("P4", 10, 12.0))
    assert slow_paragraphs(rows) == []


def test_fewer_than_three_paragraphs_give_no_reference() -> None:
    assert slow_paragraphs(paces(("P1", 10, 4.0), ("P2", 10, 400.0))) == []
    assert slow_paragraphs([]) == []


def test_paragraphs_without_words_or_time_are_ignored() -> None:
    rows = paces(("P1", 10, 4.0), ("P2", 0, 6.0), ("P3", 10, 0.0), ("P4", 10, 4.0), ("P5", 10, 4.0))
    assert slow_paragraphs(rows) == []
