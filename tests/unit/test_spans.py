from dataclasses import dataclass

import pytest
from fakes import timed_words

from vizsync.asr.base import Word
from vizsync.match.aligner import WordMatch
from vizsync.match.spans import (
    ParagraphSpan,
    ParagraphStatus,
    compute_spans,
    paragraph_confidence,
    paragraph_status,
    spans_from_alignment,
    split_matches,
)
from vizsync.script.models import Paragraph

OK = ParagraphStatus.OK
LOW = ParagraphStatus.LOW_CONFIDENCE
MISSING = ParagraphStatus.MISSING
PAUSE = 1.0


def paragraphs(*texts: str) -> list[Paragraph]:
    return [
        Paragraph(id=f"P{number}", number=number, line=number, text=text)
        for number, text in enumerate(texts, start=1)
    ]


@dataclass
class Spoken:
    """Recognized words of a narration, and the times of each spoken segment."""

    words: list[Word]
    segments: list[tuple[float, float]]

    def start(self, segment: int) -> float:
        return self.segments[segment][0]

    def end(self, segment: int) -> float:
        return self.segments[segment][1]


def speak(*segments: str, start: float = 0.5) -> Spoken:
    """Lay the segments one after the other with a pause between them (0.4 s words, 0.1 s gaps)."""
    words: list[Word] = []
    times: list[tuple[float, float]] = []
    time = start
    for text in segments:
        segment = timed_words(text, start=time)
        words.extend(segment)
        times.append((segment[0].start, segment[-1].end))
        time = segment[-1].end + PAUSE
    return Spoken(words, times)


def assert_span(span: ParagraphSpan, start: float, end: float, status: ParagraphStatus) -> None:
    assert span.start == pytest.approx(start)
    assert span.end == pytest.approx(end)
    assert span.status is status


def assert_missing(span: ParagraphSpan) -> None:
    assert span.status is MISSING
    assert span.start is None
    assert span.end is None


P1 = "Northwind opened its first warehouse in the spring."
P2 = "The new site handled orders for the whole northern region."
P3 = "By the end of the year Northwind had hired forty drivers."


# --- Known hard cases (docs/ARCHITECTURE.md) ---


def test_numbers_as_words_against_digits_keep_boundaries() -> None:
    # A year read as "twenty twenty-three" is not converted, so it stays unmatched.
    script = paragraphs(P1, "Northwind earned its first million in twenty twenty-three.", P3)
    spoken = speak(P1, "Northwind earned its first million in 2023.", P3)
    spans = compute_spans(script, spoken.words)
    assert_span(spans[0], spoken.start(0), spoken.end(0), OK)
    assert spans[1].start == pytest.approx(spoken.start(1))
    assert spans[1].end == pytest.approx(spoken.end(1))
    assert spans[1].status is not MISSING
    assert_span(spans[2], spoken.start(2), spoken.end(2), OK)


def test_number_at_paragraph_start_moves_start_back_over_the_digits() -> None:
    # "A hundred" is not converted, so it stays unmatched against "100".
    script = paragraphs("A hundred stores opened across the northern region that year.", P3)
    spoken = speak("100 stores opened across the northern region that year.", P3)
    spans = compute_spans(script, spoken.words)
    # Raw start is "stores"; moved back over the unmatched "100", never before the first word.
    assert_span(spans[0], spoken.start(0), spoken.end(0), OK)
    assert spans[0].confidence == pytest.approx(0.8)
    assert_span(spans[1], spoken.start(1), spoken.end(1), OK)


def test_spelled_out_amount_matches_recognized_digits() -> None:
    amount = "Three hundred and seventy-five million dollars."
    spoken = speak(P1, "$375 million dollars.", P3)
    spans = compute_spans(paragraphs(P1, amount, P3), spoken.words)
    assert_span(spans[0], spoken.start(0), spoken.end(0), OK)
    assert_span(spans[1], spoken.start(1), spoken.end(1), OK)
    assert spans[1].confidence == 1.0
    # One entry per normalized script word: 375, million, dollars.
    assert spans[1].word_times == tuple((word.start, word.end) for word in spoken.words[8:11])
    assert_span(spans[2], spoken.start(2), spoken.end(2), OK)


def test_spelled_out_number_across_recognized_words_is_one_word() -> None:
    amount = "Northwind shipped twenty-five thousand parcels."
    spoken = speak(P1, "Northwind shipped twenty five thousand parcels.", P3)
    spans = compute_spans(paragraphs(P1, amount, P3), spoken.words)
    assert_span(spans[1], spoken.start(1), spoken.end(1), OK)
    assert spans[1].confidence == 1.0
    twenty, thousand = spoken.words[10], spoken.words[12]
    assert spans[1].word_times[2] == (twenty.start, thousand.end)
    assert len(spans[1].word_times) == 4


def test_misheard_names_stay_matched() -> None:
    script = paragraphs(
        "Northwind bought Zume in the spring.", "Then the team moved Zume to the cloud with Zume."
    )
    spoken = speak(
        "Northwind bought Zoom in the spring.", "Then the team moved Zoomy to the cloud with Zoom."
    )
    spans = compute_spans(script, spoken.words)
    assert_span(spans[0], spoken.start(0), spoken.end(0), OK)
    assert_span(spans[1], spoken.start(1), spoken.end(1), OK)
    assert spans[0].confidence < 1.0


def test_skipped_sentence_lowers_confidence_and_leaves_others_alone() -> None:
    second = "The new site handled orders for the whole northern region."
    skipped = "It ran day and night without a single break."
    script = paragraphs(P1, f"{second} {skipped}", P3)
    spoken = speak(P1, second, P3)
    spans = compute_spans(script, spoken.words)
    assert_span(spans[0], spoken.start(0), spoken.end(0), OK)
    assert_span(spans[1], spoken.start(1), spoken.end(1), LOW)
    assert spans[1].confidence == pytest.approx(10 / 19)
    assert_span(spans[2], spoken.start(2), spoken.end(2), OK)


def test_repeated_sentence_picks_one_take() -> None:
    sentence = "Northwind hired twelve new drivers."
    rest = "The fleet grew quickly after that."
    script = paragraphs(P1, f"{sentence} {rest}", P3)
    spoken = speak(P1, sentence, f"{sentence} {rest}", P3)
    spans = compute_spans(script, spoken.words)
    assert_span(spans[0], spoken.start(0), spoken.end(0), OK)
    assert_span(spans[1], spoken.start(2), spoken.end(2), OK)  # the last take is kept
    assert spans[1].confidence == 1.0
    assert_span(spans[2], spoken.start(3), spoken.end(3), OK)


def test_whole_paragraph_missing() -> None:
    spoken = speak(P1, P3)
    spans = compute_spans(paragraphs(P1, P2, P3), spoken.words)
    assert_span(spans[0], spoken.start(0), spoken.end(0), OK)
    assert_missing(spans[1])
    assert spans[1].confidence == 0.0
    assert_span(spans[2], spoken.start(1), spoken.end(1), OK)


def test_very_short_paragraph_gets_a_span() -> None:
    spoken = speak(P1, "Northwind kept going.", P3)
    spans = compute_spans(paragraphs(P1, "Northwind kept going.", P3), spoken.words)
    assert [span.status for span in spans] == [OK, OK, OK]
    assert_span(spans[1], spoken.start(1), spoken.end(1), OK)


def test_very_short_paragraph_with_a_misheard_word_is_low_confidence() -> None:
    spoken = speak(P1, "Northwind kept quiet.", P3)
    spans = compute_spans(paragraphs(P1, "Northwind kept going.", P3), spoken.words)
    # "going" was heard as "quiet": the end moves forward by one median word (0.4 s) from "kept".
    kept_end = spoken.end(1) - 0.5
    assert_span(spans[1], spoken.start(1), kept_end + 0.4, LOW)
    assert spans[1].confidence == pytest.approx(2 / 3)
    assert_span(spans[2], spoken.start(2), spoken.end(2), OK)


def test_hallucination_in_final_silence_is_ignored() -> None:
    last = "See you in the next Northwind report."
    spoken = speak(P1, last, "Thank you for watching.")
    spans = compute_spans(paragraphs(P1, last), spoken.words)
    assert_span(spans[0], spoken.start(0), spoken.end(0), OK)
    assert_span(spans[1], spoken.start(1), spoken.end(1), OK)


OPENED = "And then Northwind opened a store in Lisbon."
CLOSED = "And then Northwind closed the store in Porto."


def test_paragraphs_with_the_same_opening_stay_apart() -> None:
    spoken = speak(OPENED, CLOSED)
    spans = compute_spans(paragraphs(OPENED, CLOSED), spoken.words)
    assert_span(spans[0], spoken.start(0), spoken.end(0), OK)
    assert_span(spans[1], spoken.start(1), spoken.end(1), OK)


@pytest.mark.parametrize("spoken_index", [0, 1])
def test_same_opening_with_one_paragraph_missing(spoken_index: int) -> None:
    texts = [OPENED, CLOSED]
    spoken = speak(texts[spoken_index])
    spans = compute_spans(paragraphs(*texts), spoken.words)
    assert_span(spans[spoken_index], spoken.start(0), spoken.end(0), OK)
    assert_missing(spans[1 - spoken_index])


# --- compute_spans in general ---


def test_no_paragraphs() -> None:
    assert compute_spans([], timed_words("northwind")) == []


def test_no_recognized_words_makes_every_paragraph_missing() -> None:
    spans = compute_spans(paragraphs(P1, P2), [])
    assert [span.id for span in spans] == ["P1", "P2"]
    for span in spans:
        assert_missing(span)
        assert span.confidence == 0.0


def test_spans_follow_script_order_and_ids() -> None:
    spoken = speak(P1, P2, P3)
    spans = compute_spans(paragraphs(P1, P2, P3), spoken.words)
    assert [span.id for span in spans] == ["P1", "P2", "P3"]
    for index, span in enumerate(spans):
        assert_span(span, spoken.start(index), spoken.end(index), OK)
        assert span.confidence == 1.0


def test_times_stay_on_the_input_timeline() -> None:
    spoken = speak(P1, P2, start=3_600.0)
    spans = compute_spans(paragraphs(P1, P2), spoken.words)
    assert_span(spans[0], 3_600.0, spoken.end(0), OK)
    assert_span(spans[1], spoken.start(1), spoken.end(1), OK)


def test_min_confidence_decides_between_ok_and_low() -> None:
    text = "Northwind bought Zume in the spring."
    spoken = speak("Northwind bought Zoom in the spring.")
    loose = compute_spans(paragraphs(text), spoken.words, min_confidence=0.5)
    strict = compute_spans(paragraphs(text), spoken.words, min_confidence=0.95)
    assert loose[0].status is OK
    assert strict[0].status is LOW
    assert loose[0].start == strict[0].start


def test_paragraph_without_words_after_normalization_is_missing() -> None:
    spoken = speak(P1)
    spans = compute_spans(paragraphs(P1, "— ..."), spoken.words)
    assert_missing(spans[1])


# --- splitting, confidence and status ---


def test_split_matches_by_paragraph_word_counts() -> None:
    matches: list[WordMatch | None] = [match(0), None, match(1), match(2), None]
    assert split_matches(matches, [2, 0, 3]) == [[match(0), None], [], [match(1), match(2), None]]


def test_split_matches_needs_counts_that_add_up() -> None:
    with pytest.raises(ValueError, match="add up"):
        split_matches([match(0)], [2])


def match(index: int, similarity: float = 1.0) -> WordMatch:
    return WordMatch(recognized_index=index, similarity=similarity)


def test_confidence_weights_matches_by_similarity() -> None:
    assert paragraph_confidence([match(0), None, match(2, 0.5), None]) == pytest.approx(0.375)


def test_confidence_of_nothing_is_zero() -> None:
    assert paragraph_confidence([]) == 0.0
    assert paragraph_confidence([None, None]) == 0.0


def test_status_missing_below_30_percent_matched() -> None:
    three_of_ten: list[WordMatch | None] = [match(i) for i in range(3)] + [None] * 7
    two_of_ten: list[WordMatch | None] = [match(i) for i in range(2)] + [None] * 8
    assert paragraph_status(three_of_ten, min_confidence=0.0) is OK
    assert paragraph_status(two_of_ten, min_confidence=0.0) is MISSING
    assert paragraph_status([None], min_confidence=0.0) is MISSING
    assert paragraph_status([], min_confidence=0.0) is MISSING


def test_status_low_confidence_below_minimum() -> None:
    four_of_five: list[WordMatch | None] = [match(i) for i in range(4)] + [None]
    assert paragraph_status(four_of_five, min_confidence=0.8) is OK
    assert paragraph_status(four_of_five, min_confidence=0.81) is LOW


def test_status_counts_weak_matches_as_matched() -> None:
    weak: list[WordMatch | None] = [match(0, 0.5), match(1, 0.5), match(2, 0.5)]
    assert paragraph_status(weak, min_confidence=0.8) is LOW


# --- spans from an alignment: boundaries and refinement ---


def grid(count: int, *, start: float = 0.0) -> list[Word]:
    """Words named w0, w1, ... lasting 0.4 s, one every 0.5 s."""
    return timed_words(" ".join(f"w{i}" for i in range(count)), start=start)


def test_span_is_first_to_last_matched_word() -> None:
    words = grid(6)
    spans = spans_from_alignment(
        ["P1", "P2"], [[match(0), match(1), match(2)], [match(3), match(4), match(5)]], words
    )
    assert spans == [
        ParagraphSpan("P1", 0.0, 1.4, 1.0, OK),
        ParagraphSpan("P2", 1.5, 2.9, 1.0, OK),
    ]


def test_leading_unmatched_words_move_start_over_unmatched_recognized_words() -> None:
    words = grid(10)
    # P2: two leading script words unmatched; recognized w4..w5 matched nothing.
    alignment: list[list[WordMatch | None]] = [
        [match(0), match(1), match(2), match(3)],
        [None, None, match(6), match(7), match(8), match(9)],
    ]
    spans = spans_from_alignment(["P1", "P2"], alignment, words, min_confidence=0.5)
    # Raw start 3.0 (w6), moved back by 2 x 0.4 s = 2.2, inside w4 (starts at 2.0).
    assert spans[1].start == pytest.approx(2.2)
    assert spans[0].end == pytest.approx(1.9)


def test_start_never_moves_before_the_unmatched_recognized_words() -> None:
    words = grid(10)
    alignment: list[list[WordMatch | None]] = [
        [match(0), match(1), match(2), match(3), match(4)],
        [None, None, None, None, match(6), match(7), match(8), match(9)],
    ]
    spans = spans_from_alignment(["P1", "P2"], alignment, words, min_confidence=0.0)
    # Wanted 3.0 - 4 x 0.4 = 1.4, but only w5 (from 2.5) is unclaimed before P2.
    assert spans[1].start == pytest.approx(2.5)


def test_no_unmatched_recognized_words_means_no_extension() -> None:
    words = grid(6)
    alignment: list[list[WordMatch | None]] = [
        [match(0), match(1), match(2), None, None],
        [match(3), match(4), match(5)],
    ]
    spans = spans_from_alignment(["P1", "P2"], alignment, words, min_confidence=0.0)
    assert spans[0].end == pytest.approx(1.4)
    assert spans[1].start == pytest.approx(1.5)


def test_both_neighbours_extending_share_the_gap_without_overlap() -> None:
    words = grid(8)
    # w3, w4 unmatched between P1 (ends 1.4) and P2 (starts 2.5).
    alignment: list[list[WordMatch | None]] = [
        [match(0), match(1), match(2), None, None, None],
        [None, None, None, match(5), match(6), match(7)],
    ]
    spans = spans_from_alignment(["P1", "P2"], alignment, words, min_confidence=0.0)
    # Each may extend 1.0 s (over w3..w4); together that overlaps, so the 1.1 s gap between
    # them is split in proportion to their extensions: 0.55 s each.
    assert spans[0].end == pytest.approx(1.95)
    assert spans[1].start == pytest.approx(1.95)


def test_first_paragraph_start_bounded_by_first_recognized_word() -> None:
    words = grid(5, start=10.0)
    alignment: list[list[WordMatch | None]] = [[None, None, None, match(1), match(2), match(3)]]
    spans = spans_from_alignment(["P1"], alignment, words, min_confidence=0.0)
    assert spans[0].start == pytest.approx(10.0)


def test_last_paragraph_end_bounded_by_last_recognized_word() -> None:
    words = grid(5)
    alignment: list[list[WordMatch | None]] = [[match(0), match(1), match(2), None, None, None]]
    spans = spans_from_alignment(["P1"], alignment, words, min_confidence=0.0)
    assert spans[0].end == pytest.approx(2.4)


def test_refinement_uses_median_word_duration_of_the_paragraph() -> None:
    words = [
        Word(text="a", start=0.0, end=0.2),
        Word(text="b", start=0.3, end=0.5),
        Word(text="c", start=1.0, end=1.3),
        Word(text="d", start=1.4, end=1.7),
        Word(text="e", start=1.8, end=2.6),
    ]
    alignment: list[list[WordMatch | None]] = [[None, match(2), match(3), match(4)]]
    spans = spans_from_alignment(["P1"], alignment, words, min_confidence=0.0)
    # Median of 0.3, 0.3, 0.8 is 0.3.
    assert spans[0].start == pytest.approx(0.7)


def test_missing_neighbour_is_skipped_when_bounding() -> None:
    words = grid(10)
    alignment: list[list[WordMatch | None]] = [
        [match(0), match(1), match(2)],
        [None] * 6,
        [None, match(7), match(8), match(9)],
    ]
    spans = spans_from_alignment(["P1", "P2", "P3"], alignment, words, min_confidence=0.0)
    assert_missing(spans[1])
    # P3 moves back one median word (0.4 s) from w7 (3.5), into the unmatched w3..w6.
    assert spans[2].start == pytest.approx(3.1)
    assert spans[0].end == pytest.approx(1.4)


def test_missing_paragraph_never_gets_times_even_with_a_few_matches() -> None:
    words = grid(10)
    alignment: list[list[WordMatch | None]] = [[match(4)] + [None] * 9]
    spans = spans_from_alignment(["P1"], alignment, words)
    assert_missing(spans[0])
    assert spans[0].confidence == pytest.approx(0.1)


def test_spans_from_alignment_needs_one_match_list_per_paragraph() -> None:
    with pytest.raises(ValueError, match="one match list per paragraph"):
        spans_from_alignment(["P1", "P2"], [[match(0)]], grid(1))
