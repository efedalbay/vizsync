from itertools import pairwise

import pytest

from vizsync.asr.base import Word
from vizsync.asr.snap import MAX_PULL_SECONDS, MIN_PULL_SECONDS, snap_words_to_speech


def word(text: str, start: float, end: float) -> Word:
    return Word(text=text, start=start, end=end)


def times(words: list[Word]) -> list[tuple[float, float]]:
    return [(item.start, item.end) for item in words]


def test_the_first_word_after_a_long_silence_starts_with_the_speech() -> None:
    # The fixture clip: "18" of P8 swallowed 0.4 s of the silence before it.
    snapped = snap_words_to_speech([word("18", 32.39, 33.27)], [(32.80, 36.05)])
    assert snapped == [word("18", 32.80, 33.27)]


def test_a_word_inside_its_segment_is_untouched() -> None:
    words = [word("Northwind", 10.2, 10.7), word("grew", 10.7, 11.0)]
    assert snap_words_to_speech(words, [(10.0, 14.0)]) == words


def test_a_difference_below_the_tolerance_is_untouched() -> None:
    words = [word("Northwind", 9.97, 14.03)]
    assert snap_words_to_speech(words, [(10.0, 14.0)]) == words


def test_a_difference_of_exactly_the_tolerance_is_snapped() -> None:
    snapped = snap_words_to_speech([word("Northwind", 9.75, 10.5)], [(10.0, 14.0)], tolerance=0.25)
    assert times(snapped) == [(10.0, 10.5)]


def test_the_tolerance_can_be_changed() -> None:
    words = [word("Northwind", 9.5, 10.5)]
    assert snap_words_to_speech(words, [(10.0, 14.0)], tolerance=0.75) == words
    assert times(snap_words_to_speech(words, [(10.0, 14.0)], tolerance=0.25)) == [(10.0, 10.5)]


def test_an_end_stretched_into_the_silence_is_cut_back() -> None:
    snapped = snap_words_to_speech([word("bankruptcy", 35.6, 36.7)], [(32.80, 36.05)])
    assert snapped == [word("bankruptcy", 35.6, 36.05)]


def test_a_word_in_the_silence_is_untouched() -> None:
    words = [word("um", 14.1, 14.4)]
    assert snap_words_to_speech(words, [(10.0, 14.0), (14.6, 19.0)]) == words


def test_a_word_after_the_last_segment_is_untouched() -> None:
    words = [word("thanks", 20.0, 20.5)]
    assert snap_words_to_speech(words, [(10.0, 14.0)]) == words


def test_a_word_over_two_segments_keeps_to_the_one_it_starts_in() -> None:
    snapped = snap_words_to_speech([word("later", 13.6, 15.2)], [(10.0, 14.0), (14.6, 19.0)])
    assert times(snapped) == [(13.6, 14.0)]


def test_a_word_from_the_silence_over_two_segments_keeps_to_the_first() -> None:
    snapped = snap_words_to_speech([word("later", 9.5, 15.2)], [(10.0, 14.0), (14.6, 19.0)])
    assert times(snapped) == [(10.0, 14.0)]


def test_a_short_pause_between_two_paragraphs_is_kept_free_of_words() -> None:
    # Real videos have about 0.6 s between paragraphs.
    segments = [(10.0, 14.0), (14.6, 19.0)]
    words = [
        word("revenue", 13.0, 13.5),
        word("doubled.", 13.5, 14.4),
        word("Then", 14.05, 14.9),
        word("came", 14.9, 15.2),
    ]
    assert times(snap_words_to_speech(words, segments)) == [
        (13.0, 13.5),
        (13.5, 14.0),
        (14.6, 14.9),
        (14.9, 15.2),
    ]


def test_a_snap_that_would_leave_almost_nothing_of_the_word_is_not_made() -> None:
    words = [word("a", 14.05, 14.61), word("b", 13.99, 14.9)]
    assert snap_words_to_speech(words[:1], [(14.6, 19.0)]) == words[:1]
    assert snap_words_to_speech(words[1:], [(10.0, 14.0)]) == words[1:]


def test_a_snap_that_leaves_the_minimum_length_is_made() -> None:
    snapped = snap_words_to_speech([word("a", 14.0, 14.65)], [(14.6, 19.0)])
    assert times(snapped) == [(14.6, 14.65)]


def test_order_is_kept_and_no_overlap_is_created() -> None:
    segments = [(0.5, 2.0), (2.3, 2.6), (3.0, 6.0), (8.0, 9.0)]
    words = [
        word("one", 0.0, 0.9),
        word("two", 0.9, 2.4),
        word("three", 2.4, 2.9),
        word("four", 2.9, 3.5),
        word("five", 3.5, 7.0),
        word("six", 7.0, 7.5),
        word("seven", 7.5, 9.6),
    ]
    snapped = snap_words_to_speech(words, segments)
    assert [item.text for item in snapped] == [item.text for item in words]
    for item in snapped:
        assert item.end - item.start >= 0.02
    for before, after in pairwise(snapped):
        assert before.end <= after.start
    for original, item in zip(words, snapped, strict=True):
        assert original.start <= item.start and item.end <= original.end


def test_every_word_finds_its_own_segment_in_a_long_recording() -> None:
    segments = [(float(n), n + 0.5) for n in range(2000)]
    words = [word(str(n), n - 0.2, n + 0.7) for n in range(2000)]
    snapped = snap_words_to_speech(words, segments)
    assert times(snapped) == [(float(n), n + 0.5) for n in range(2000)]


@pytest.mark.parametrize(
    ("words", "segments"),
    [([], []), ([], [(1.0, 2.0)]), ([word("Northwind", 1.0, 2.0)], [])],
)
def test_empty_inputs(words: list[Word], segments: list[tuple[float, float]]) -> None:
    assert snap_words_to_speech(words, segments) == words


def test_the_input_is_not_changed() -> None:
    words = [word("18", 32.39, 33.27)]
    snapped = snap_words_to_speech(words, [(32.80, 36.05)])
    assert words == [word("18", 32.39, 33.27)]
    assert snapped is not words


# --- The first word of a stretch of speech -------------------------------------------------------


def test_a_numeral_timed_late_starts_with_the_speech() -> None:
    # Real data, model small.en: "Sixty-seven percent" was recognized as "67%." timed at its end.
    words = [word("67%.", 1.12, 1.72), word("That's", 1.72, 2.32)]
    snapped = snap_words_to_speech(words, [(0.13, 1.50), (2.05, 8.35)])
    assert snapped == [word("67%.", 0.13, 1.50), word("That's", 2.05, 2.32)]


def test_the_first_word_after_a_short_pause_between_paragraphs_is_pulled() -> None:
    # Real videos have about 0.6 s between paragraphs.
    segments = [(10.0, 14.0), (14.6, 19.0)]
    words = [word("doubled.", 13.5, 14.0), word("Then", 15.0, 15.4), word("came", 15.4, 15.7)]
    assert times(snap_words_to_speech(words, segments)) == [
        (13.5, 14.0),
        (14.6, 15.4),
        (15.4, 15.7),
    ]


def test_the_pull_limits_are_the_documented_ones() -> None:
    assert (MIN_PULL_SECONDS, MAX_PULL_SECONDS) == (0.3, 2.0)


@pytest.mark.parametrize("start", [10.3, 12.0])
def test_a_pull_of_exactly_a_limit_is_made(start: float) -> None:
    snapped = snap_words_to_speech([word("Northwind", start, 12.5)], [(10.0, 14.0)])
    assert times(snapped) == [(10.0, 12.5)]


@pytest.mark.parametrize("start", [10.29, 12.01])
def test_a_pull_just_outside_the_limits_is_not_made(start: float) -> None:
    words = [word("Northwind", start, 12.5)]
    assert snap_words_to_speech(words, [(10.0, 14.0)]) == words


def test_a_pull_longer_than_the_limit_is_not_shortened_to_the_limit() -> None:
    words = [word("Northwind", 13.0, 13.5)]
    assert snap_words_to_speech(words, [(10.0, 14.0)]) == words


def test_the_pull_limits_can_be_changed() -> None:
    words = [word("Northwind", 10.5, 11.0)]
    assert snap_words_to_speech(words, [(10.0, 14.0)], min_pull=0.75) == words
    assert snap_words_to_speech(words, [(10.0, 14.0)], max_pull=0.25) == words
    assert times(snap_words_to_speech(words, [(10.0, 14.0)], min_pull=0.25)) == [(10.0, 11.0)]


def test_only_the_first_word_of_a_stretch_of_speech_is_pulled() -> None:
    words = [word("Northwind", 10.1, 10.6), word("grew", 11.5, 12.0)]
    assert snap_words_to_speech(words, [(10.0, 14.0)]) == words


def test_a_late_second_word_is_not_pulled_after_a_first_word_moved_later() -> None:
    words = [word("So", 9.5, 9.8), word("Northwind", 10.5, 11.0)]
    assert times(snap_words_to_speech(words, [(9.7, 14.0)])) == [(9.7, 9.8), (10.5, 11.0)]


def test_a_pull_stops_at_the_end_of_the_previous_word() -> None:
    # "doubled." keeps its end: cutting it at 14.0 would leave less than 0.02 s of it.
    segments = [(10.0, 14.0), (14.6, 19.0)]
    words = [word("doubled.", 13.99, 14.7), word("Then", 15.0, 15.4)]
    assert times(snap_words_to_speech(words, segments)) == [(13.99, 14.7), (14.7, 15.4)]


def test_a_pull_stops_at_the_end_of_a_word_in_the_silence() -> None:
    segments = [(10.0, 14.0), (14.6, 19.0)]
    words = [word("um", 14.1, 14.6), word("Then", 15.0, 15.4)]
    snapped = snap_words_to_speech(words, segments)
    assert snapped[0] == words[0]
    assert times(snapped) == [(14.1, 14.6), (14.6, 15.4)]


def test_a_word_in_the_silence_is_not_the_first_word_of_the_next_speech() -> None:
    segments = [(10.0, 14.0), (14.6, 19.0)]
    words = [word("um", 14.1, 14.4), word("Then", 15.0, 15.4)]
    assert times(snap_words_to_speech(words, segments)) == [(14.1, 14.4), (14.6, 15.4)]


def test_a_word_in_the_silence_is_never_pulled() -> None:
    words = [word("um", 14.3, 14.5)]
    assert snap_words_to_speech(words, [(10.0, 14.0), (14.6, 19.0)]) == words


def test_a_pulled_word_keeps_the_end_the_inward_rule_gives_it() -> None:
    # Cutting the end at 1.50 would leave 0.01 s of the word, so today's rule keeps 1.72.
    snapped = snap_words_to_speech([word("67%.", 1.49, 1.72)], [(0.13, 1.50)])
    assert times(snapped) == [(0.13, 1.72)]


def test_a_pull_is_not_made_when_the_previous_word_ends_after_the_start() -> None:
    # Recognized words can overlap; the pull never moves a start later.
    words = [word("doubled.", 13.99, 15.2), word("Then", 15.0, 15.4)]
    assert snap_words_to_speech(words, [(10.0, 14.0), (14.6, 19.0)]) == words


def test_pulls_keep_the_order_and_create_no_overlap() -> None:
    segments = [(0.13, 1.50), (2.05, 8.35), (9.0, 12.0), (12.6, 20.0)]
    words = [
        word("67%.", 1.12, 1.72),
        word("That's", 1.72, 2.32),
        word("a", 2.32, 2.5),
        word("lot.", 2.5, 8.6),
        word("um", 8.6, 8.9),
        word("Northwind", 9.5, 10.0),
        word("grew", 10.0, 11.0),
        word("fast.", 11.0, 12.3),
        word("Then", 15.0, 15.5),
        word("came", 15.5, 16.0),
    ]
    snapped = snap_words_to_speech(words, segments)
    assert times(snapped) == [
        (0.13, 1.50),
        (2.05, 2.32),
        (2.32, 2.5),
        (2.5, 8.35),
        (8.6, 8.9),
        (9.0, 10.0),
        (10.0, 11.0),
        (11.0, 12.0),
        (15.0, 15.5),
        (15.5, 16.0),
    ]
    assert [item.text for item in snapped] == [item.text for item in words]
    for item in snapped:
        assert item.end - item.start >= 0.02
    for before, after in pairwise(snapped):
        assert before.end <= after.start


def test_every_first_word_is_pulled_in_a_long_recording() -> None:
    segments = [(float(n), n + 0.9) for n in range(2000)]
    words = [word(str(n), n + 0.5, n + 0.8) for n in range(2000)]
    snapped = snap_words_to_speech(words, segments)
    assert times(snapped) == [(float(n), n + 0.8) for n in range(2000)]


def test_a_pulled_word_is_a_new_word() -> None:
    words = [word("67%.", 1.12, 1.72)]
    snapped = snap_words_to_speech(words, [(0.13, 1.50)])
    assert words == [word("67%.", 1.12, 1.72)]
    assert snapped[0] is not words[0]
