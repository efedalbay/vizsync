import random

import pytest

from vizsync.match import aligner
from vizsync.match.aligner import NEAR_MATCH_THRESHOLD, WordMatch, align, word_similarity


def words(text: str) -> list[str]:
    return text.split()


def indices(matches: list[WordMatch | None]) -> list[int | None]:
    return [None if match is None else match.recognized_index for match in matches]


def assert_strictly_increasing(matches: list[WordMatch | None]) -> None:
    found = [match.recognized_index for match in matches if match is not None]
    assert found == sorted(set(found))


def test_word_similarity_of_identical_words_is_one() -> None:
    assert word_similarity("northwind", "northwind") == 1.0


def test_word_similarity_of_misheard_name_is_a_near_match() -> None:
    for heard in ("zoom", "zoomy"):
        similarity = word_similarity("zume", heard)
        assert NEAR_MATCH_THRESHOLD <= similarity < 1.0


def test_word_similarity_of_unrelated_words_is_below_threshold() -> None:
    assert word_similarity("lisbon", "porto") < NEAR_MATCH_THRESHOLD
    assert word_similarity("twenty", "25000") == 0.0


def test_identical_sequences_match_one_to_one() -> None:
    script = words("northwind sold twelve trucks in may")
    matches = align(script, script)
    assert matches == [WordMatch(index, 1.0) for index in range(len(script))]


def test_empty_inputs() -> None:
    assert align([], []) == []
    assert align([], ["northwind"]) == []
    assert align(["northwind", "grew"], []) == [None, None]


def test_word_missing_from_recognition_is_unmatched() -> None:
    matches = align(words("northwind sold twelve trucks"), words("northwind sold trucks"))
    assert indices(matches) == [0, 1, None, 2]


def test_extra_recognized_word_is_skipped() -> None:
    matches = align(words("northwind sold trucks"), words("northwind um sold trucks"))
    assert indices(matches) == [0, 2, 3]


def test_near_match_is_matched_with_lower_similarity() -> None:
    matches = align(words("northwind bought zume"), words("northwind bought zoomy"))
    assert indices(matches) == [0, 1, 2]
    last = matches[2]
    assert last is not None
    assert NEAR_MATCH_THRESHOLD <= last.similarity < 1.0


def test_dissimilar_substitution_is_unmatched() -> None:
    matches = align(words("northwind sold lisbon stores"), words("northwind sold porto stores"))
    assert indices(matches) == [0, 1, None, 3]


def test_order_constraint_allows_only_increasing_indices() -> None:
    matches = align(words("a b c"), words("c b a"))
    assert sum(match is not None for match in matches) == 1
    assert_strictly_increasing(matches)


def test_trailing_hallucination_is_skipped() -> None:
    script = words("see you in the next northwind report")
    heard = script + words("thank you for watching")
    assert indices(align(script, heard)) == list(range(len(script)))


def test_repeated_sentence_keeps_the_last_take() -> None:
    script = words("northwind hired twelve drivers the fleet grew")
    heard = words("northwind hired twelve drivers northwind hired twelve drivers the fleet grew")
    assert indices(align(script, heard)) == [4, 5, 6, 7, 8, 9, 10]


def test_paragraphs_with_the_same_opening_stay_apart() -> None:
    first = words("and then northwind opened a store in lisbon")
    second = words("and then northwind closed the store in porto")
    matches = align(first + second, second)
    assert indices(matches) == [None] * 8 + list(range(8))


def _sentence(number: int) -> list[str]:
    return words(f"northwind report {number} part {number * 7} item {number * 13}")


def test_long_block_missing_at_the_start_of_recognition() -> None:
    script = [word for number in range(60) for word in _sentence(number)]
    heard = script[300:]
    matches = align(script, heard)
    assert indices(matches) == [None] * 300 + list(range(len(heard)))


def test_drift_without_length_difference_is_followed() -> None:
    # 120 extra words at the start, 120 script words never spoken at the end: same lengths,
    # but the path leaves the main diagonal by 120 words.
    script = [word for number in range(80) for word in _sentence(number)]
    heard = [f"noise{number}" for number in range(120)] + script[:-120]
    assert len(script) == len(heard)
    matches = align(script, heard)
    expected: list[int | None] = [index + 120 for index in range(len(script) - 120)]
    assert indices(matches) == expected + [None] * 120


@pytest.mark.parametrize(
    ("script", "heard"),
    [
        (words("a b c d e f"), words("x y z")),
        (words("a a a a"), words("a a")),
        (words("a"), words("b a b a b")),
    ],
)
def test_output_has_one_entry_per_script_word_in_order(script: list[str], heard: list[str]) -> None:
    matches = align(script, heard)
    assert len(matches) == len(script)
    assert_strictly_increasing(matches)
    for script_word, match in zip(script, matches, strict=True):
        if match is not None:
            assert match.similarity == word_similarity(script_word, heard[match.recognized_index])


def test_narrow_band_gives_the_same_result_as_the_full_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng = random.Random(7)
    vocabulary = words("northwind sold zume zoom item part report march 25 store lisbon and the")
    for _ in range(150):
        script = rng.choices(vocabulary, k=rng.randint(1, 60))
        heard = [word for word in script if rng.random() > 0.15]
        for _ in range(rng.randint(0, 10)):
            heard.insert(rng.randrange(len(heard) + 1), rng.choice(vocabulary))
        monkeypatch.setattr(aligner, "BAND_MARGIN", 0)
        banded = align(script, heard)
        monkeypatch.setattr(aligner, "BAND_MARGIN", 1_000_000)
        assert banded == align(script, heard)
