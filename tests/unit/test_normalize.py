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
    ["north-east", "north\u2010east", "north\u2013east", "north \u2014 east", "north/east"],
)
def test_splits_on_hyphens_dashes_and_slashes(text: str) -> None:
    assert normalize_text(text) == ["north", "east"]


def test_applies_nfkc() -> None:
    assert normalize_text("\ufb01nal \uff12\uff15 units") == ["final", "25", "units"]


def test_casefold_handles_non_ascii_letters() -> None:
    assert normalize_text("STRASSE Stra\u00dfe") == ["strasse", "strasse"]


def test_digits_are_kept_as_written() -> None:
    assert normalize_text("25 twenty 3") == ["25", "20", "3"]
    assert normalize_text("375 25,000 3.5 007") == ["375", "25000", "3.5", "007"]


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
    result = normalize_words([Word(text="door-to-door", start=3.0, end=3.6)])
    assert [w.text for w in result] == ["door", "to", "door"]
    assert [w.start for w in result] == pytest.approx([3.0, 3.2, 3.4])
    assert [w.end for w in result] == pytest.approx([3.2, 3.4, 3.6])
    assert result[-1].end == 3.6


def test_normalize_words_of_nothing() -> None:
    assert normalize_words([]) == []


# --- Spelled-out numbers become digits ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("zero", ["0"]),
        ("one", ["1"]),
        ("seven", ["7"]),
        ("ten", ["10"]),
        ("thirteen", ["13"]),
        ("nineteen", ["19"]),
        ("forty", ["40"]),
        ("twenty-five", ["25"]),
        ("ninety nine", ["99"]),
        ("one hundred", ["100"]),
        ("three hundred and seventy-five", ["375"]),
        ("three hundred seventy-five", ["375"]),
        ("nine hundred and nine", ["909"]),
        ("two hundred twelve", ["212"]),
    ],
)
def test_cardinals_below_a_thousand_become_digits(text: str, expected: list[str]) -> None:
    assert normalize_text(text) == expected


def test_the_spoken_amount_of_the_real_case() -> None:
    assert normalize_text("> Three hundred and seventy-five million dollars.") == [
        "375",
        "million",
        "dollars",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("twenty-five thousand", ["25000"]),
        ("two thousand five hundred", ["2500"]),
        ("five hundred thousand", ["500000"]),
        ("two hundred and fifty thousand", ["250000"]),
        ("nine hundred ninety-nine thousand nine hundred ninety-nine", ["999999"]),
        ("two thousand and five", ["2005"]),
        ("forty thousand twelve", ["40012"]),
    ],
)
def test_thousand_is_absorbed_into_the_digits(text: str, expected: list[str]) -> None:
    assert normalize_text(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("three hundred seventy-five million", ["375", "million"]),
        ("two point five million", ["2.5", "million"]),
        ("four billion dollars", ["4", "billion", "dollars"]),
        ("twelve trillion", ["12", "trillion"]),
    ],
)
def test_million_billion_and_trillion_stay_separate_words(text: str, expected: list[str]) -> None:
    assert normalize_text(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("two point five", ["2.5"]),
        ("three point one four", ["3.14"]),
        ("zero point five", ["0.5"]),
        ("one point oh five", ["1.05"]),
        ("ten point zero", ["10.0"]),
        ("twenty-five thousand point five", ["25000.5"]),
    ],
)
def test_point_followed_by_digit_words_is_a_decimal(text: str, expected: list[str]) -> None:
    assert normalize_text(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("the point is", ["the", "point", "is"]),
        ("point five", ["point", "5"]),
        ("two point", ["2", "point"]),
        ("two point twenty", ["2", "point", "20"]),
        ("Northwind's point of view", ["northwind's", "point", "of", "view"]),
    ],
)
def test_point_without_a_number_on_both_sides_stays_a_word(text: str, expected: list[str]) -> None:
    assert normalize_text(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("two and three", ["2", "and", "3"]),
        ("one hundred and Northwind", ["100", "and", "northwind"]),
        ("one hundred and two hundred", ["100", "and", "200"]),
        ("two thousand and three thousand", ["2000", "and", "3000"]),
        ("two thousand and five hundred", ["2000", "and", "500"]),
        ("fast and cheap", ["fast", "and", "cheap"]),
        ("and five", ["and", "5"]),
    ],
)
def test_and_is_consumed_only_inside_a_number(text: str, expected: list[str]) -> None:
    assert normalize_text(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("twenty twenty-six", ["20", "26"]),
        ("five five", ["5", "5"]),
        ("one two three", ["1", "2", "3"]),
        ("nineteen ninety-nine", ["19", "99"]),
        ("fifteen five", ["15", "5"]),
        ("twenty-five hundred", ["25", "hundred"]),
        ("one hundred two hundred", ["100", "200"]),
        ("two thousand three thousand", ["2000", "3000"]),
        ("zero five", ["0", "5"]),
    ],
)
def test_words_that_cannot_extend_a_number_start_a_new_one(text: str, expected: list[str]) -> None:
    assert normalize_text(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a hundred trucks", ["a", "hundred", "trucks"]),
        ("a thousand", ["a", "thousand"]),
        ("a million", ["a", "million"]),
        ("hundred thousand", ["hundred", "thousand"]),
        ("oh no", ["oh", "no"]),
        ("the first quarter", ["the", "first", "quarter"]),
        ("twenty-first", ["20", "first"]),
        ("half a million", ["half", "a", "million"]),
        ("someone often eleventh", ["someone", "often", "eleventh"]),
        ("one-time", ["1", "time"]),
    ],
)
def test_words_outside_the_number_grammar_stay_as_they_are(text: str, expected: list[str]) -> None:
    assert normalize_text(text) == expected


def test_digit_tokens_next_to_number_words_are_untouched() -> None:
    assert normalize_text("$375 million") == ["375", "million"]
    assert normalize_text("3 point 5") == ["3", "point", "5"]
    assert normalize_text("25 thousand") == ["25", "thousand"]


def test_normalize_words_merges_a_number_across_words() -> None:
    words = [
        Word(text=" Northwind", start=0.0, end=0.4),
        Word(text=" sold", start=0.5, end=0.8),
        Word(text=" three", start=0.9, end=1.1),
        Word(text=" hundred", start=1.2, end=1.5),
        Word(text=" and", start=1.6, end=1.7),
        Word(text=" seventy-five", start=1.8, end=2.4),
        Word(text=" trucks.", start=2.5, end=2.9),
    ]
    assert normalize_words(words) == [
        Word(text="northwind", start=0.0, end=0.4),
        Word(text="sold", start=0.5, end=0.8),
        Word(text="375", start=0.9, end=2.4),
        Word(text="trucks", start=2.5, end=2.9),
    ]


def test_normalize_words_merges_part_of_a_split_word() -> None:
    words = [
        Word(text=" a", start=1.0, end=1.1),
        Word(text=" forty-five-minute", start=2.0, end=2.6),
        Word(text=" call", start=2.7, end=3.0),
    ]
    result = normalize_words(words)
    assert [w.text for w in result] == ["a", "45", "minute", "call"]
    assert [w.start for w in result] == pytest.approx([1.0, 2.0, 2.4, 2.7])
    assert [w.end for w in result] == pytest.approx([1.1, 2.4, 2.6, 3.0])


def test_normalize_words_merges_into_the_first_part_of_a_split_word() -> None:
    words = [
        Word(text=" twenty", start=0.0, end=0.3),
        Word(text=" one-time", start=0.4, end=0.8),
    ]
    result = normalize_words(words)
    assert [w.text for w in result] == ["21", "time"]
    assert [w.start for w in result] == pytest.approx([0.0, 0.6])
    assert [w.end for w in result] == pytest.approx([0.6, 0.8])


def test_normalize_words_merges_a_decimal_and_drops_punctuation_words() -> None:
    words = [
        Word(text=" two", start=5.0, end=5.2),
        Word(text=" point", start=5.3, end=5.5),
        Word(text=" ...", start=5.5, end=5.6),
        Word(text=" five", start=5.7, end=5.9),
        Word(text=" million.", start=6.0, end=6.4),
        Word(text=" -", start=6.4, end=6.5),
    ]
    assert normalize_words(words) == [
        Word(text="2.5", start=5.0, end=5.9),
        Word(text="million", start=6.0, end=6.4),
    ]


def test_normalize_words_keeps_recognized_digits() -> None:
    words = [
        Word(text=" $375", start=0.0, end=0.6),
        Word(text=" million", start=0.7, end=1.0),
        Word(text=" dollars.", start=1.1, end=1.5),
    ]
    assert normalize_words(words) == [
        Word(text="375", start=0.0, end=0.6),
        Word(text="million", start=0.7, end=1.0),
        Word(text="dollars", start=1.1, end=1.5),
    ]


def test_normalize_words_times_stay_in_order() -> None:
    text = "Northwind had twenty twenty-six trucks and two point five million in one-time costs"
    words = [
        Word(text=f" {token}", start=index * 0.5, end=index * 0.5 + 0.4)
        for index, token in enumerate(text.split())
    ]
    result = normalize_words(words)
    assert [w.text for w in result] == normalize_text(text)
    assert all(w.start <= w.end for w in result)
    assert all(a.end <= b.start for a, b in zip(result, result[1:], strict=False))
