import pytest

from vizsync.asr.base import Word
from vizsync.match.normalize import normalize_text, normalize_words


def test_casefolds_and_removes_punctuation() -> None:
    assert normalize_text("Northwind, Grew FAST!") == ["northwind", "grew", "fast"]


def test_keeps_apostrophes_inside_words() -> None:
    assert normalize_text("Northwind's drivers don't stop") == [
        "northwind's",
        "drivers",
        "don't",
        "stop",
    ]


def test_typographic_apostrophe_is_a_plain_one() -> None:
    assert normalize_text("Northwind\u2019s") == normalize_text("Northwind's") == ["northwind's"]


def test_drops_apostrophes_at_word_edges() -> None:
    assert normalize_text("the drivers' trucks in the '90s") == [
        "the",
        "drivers",
        "trucks",
        "in",
        "the",
        "90s",
    ]


def test_quotes_and_brackets_are_removed() -> None:
    assert normalize_text("\u201cNorthwind\u201d (the company) \u2018won\u2019") == [
        "northwind",
        "the",
        "company",
        "won",
    ]


@pytest.mark.parametrize(
    "text",
    ["twenty-five", "twenty\u2010five", "twenty\u2013five", "twenty \u2014 five", "twenty/five"],
)
def test_splits_on_hyphens_dashes_and_slashes(text: str) -> None:
    assert normalize_text(text) == ["twenty", "five"]


def test_applies_nfkc() -> None:
    assert normalize_text("\ufb01nal \uff12\uff15 units") == ["final", "25", "units"]


def test_casefold_handles_non_ascii_letters() -> None:
    assert normalize_text("STRASSE Stra\u00dfe") == ["strasse", "strasse"]


def test_digits_are_kept_as_written() -> None:
    assert normalize_text("25 twenty 3") == ["25", "twenty", "3"]


def test_comma_between_digits_is_a_thousands_separator() -> None:
    assert normalize_text("25,000 and 25000") == ["25000", "and", "25000"]


def test_point_between_digits_is_a_decimal_point() -> None:
    assert normalize_text("3.5 million, not 35.") == ["3.5", "million", "not", "35"]


def test_other_symbols_are_removed() -> None:
    assert normalize_text("$25 is 40% of 1:30") == ["25", "is", "40", "of", "130"]


@pytest.mark.parametrize("text", ["", "   ", "...", " - ", "\u2014", "!?", "'"])
def test_empty_or_punctuation_only_gives_no_words(text: str) -> None:
    assert normalize_text(text) == []


def test_normalize_words_keeps_times_of_simple_words() -> None:
    words = [Word(text=" Northwind,", start=1.0, end=1.4), Word(text="Grew", start=1.5, end=1.8)]
    assert normalize_words(words) == [
        Word(text="northwind", start=1.0, end=1.4),
        Word(text="grew", start=1.5, end=1.8),
    ]


def test_normalize_words_drops_punctuation_only_words() -> None:
    words = [Word(text="Hi", start=0.0, end=0.2), Word(text=" -", start=0.2, end=0.3)]
    assert normalize_words(words) == [Word(text="hi", start=0.0, end=0.2)]


def test_normalize_words_splits_hyphenated_word_evenly() -> None:
    result = normalize_words([Word(text="twenty-five-six", start=3.0, end=3.6)])
    assert [w.text for w in result] == ["twenty", "five", "six"]
    assert [w.start for w in result] == pytest.approx([3.0, 3.2, 3.4])
    assert [w.end for w in result] == pytest.approx([3.2, 3.4, 3.6])
    assert result[-1].end == 3.6


def test_normalize_words_of_nothing() -> None:
    assert normalize_words([]) == []
