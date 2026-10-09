import pytest

from vizsync.match.spans import ParagraphStatus
from vizsync.output.srt import (
    MAX_CUE_SECONDS,
    MAX_LINE_CHARS,
    MIN_CUE_SECONDS,
    Cue,
    build_captions,
    format_srt,
    format_srt_time,
    write_srt,
)
from vizsync.pipeline import ParagraphResult

OK = ParagraphStatus.OK


def paragraph(
    name: str,
    text: str,
    start: float | None,
    end: float | None,
    word_times: list[tuple[float, float] | None] | None = None,
    status: ParagraphStatus = OK,
) -> ParagraphResult:
    return ParagraphResult(
        name, "Chapter", start, end, 1.0, status, text=text, word_times=tuple(word_times or ())
    )


def spoken(text: str, start: float, per_word: float = 0.4) -> list[tuple[float, float] | None]:
    """A time for each word of ``text``, one after the other (no punctuation-only tokens)."""
    return [(start + i * per_word, start + (i + 1) * per_word) for i in range(len(text.split()))]


def texts(cues: list[Cue]) -> list[str]:
    return [cue.text for cue in cues]


# --- Time format ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0.0, "00:00:00,000"),
        (1.2346, "00:00:01,235"),
        (59.9996, "00:01:00,000"),
        (61.5, "00:01:01,500"),
        (3725.04, "01:02:05,040"),
    ],
)
def test_srt_times_have_a_comma_and_milliseconds(seconds: float, text: str) -> None:
    assert format_srt_time(seconds) == text


# --- Splitting the text -----------------------------------------------------------------------


def test_a_short_paragraph_is_one_cue_on_one_line() -> None:
    text = "Then one decision changed everything."
    cues = build_captions([paragraph("P1", text, 0.4, 3.9)])
    assert [(c.start, c.end, c.text) for c in cues] == [(0.4, 3.9, text)]


def test_a_sentence_of_more_than_one_line_stays_one_cue_on_two_lines() -> None:
    text = "Northwind was worth 740 million dollars at its peak."
    (cue,) = build_captions([paragraph("P1", text, 0.4, 3.9)])
    assert cue.text.count("\n") == 1 and cue.text.replace("\n", " ") == text


def test_each_sentence_is_its_own_cue() -> None:
    text = "Then one decision changed everything. The team grew quickly after that."
    words = spoken(text, 1.0)
    cues = build_captions([paragraph("P2", text, 1.0, 1.0 + 0.4 * len(words), words)])
    assert texts(cues) == [
        "Then one decision changed everything.",
        "The team grew quickly after that.",
    ]


def test_a_cue_over_one_line_is_broken_into_two_balanced_lines() -> None:
    text = "The company started in 2016 with a small team and a big idea."
    assert len(text) > MAX_LINE_CHARS
    (cue,) = build_captions([paragraph("P3", text, 0.0, 6.0)])
    first, second = cue.text.split("\n")
    assert first + " " + second == text
    assert max(len(first), len(second)) <= MAX_LINE_CHARS
    assert abs(len(first) - len(second)) <= 12


def test_a_long_sentence_is_split_at_a_comma_into_cues_of_two_lines_at_most() -> None:
    text = (
        "When the biggest customer left, revenue fell by a third in a single quarter, "
        "and the team that had grown so quickly had to shrink just as fast, "
        "because nothing else was paying the bills."
    )
    cues = build_captions([paragraph("P4", text, 0.0, 14.0)])
    assert len(cues) >= 2
    for cue in cues:
        lines = cue.text.split("\n")
        assert len(lines) <= 2
        assert all(len(line) <= MAX_LINE_CHARS for line in lines)
    assert " ".join(" ".join(cue.text.split("\n")) for cue in cues) == text
    assert cues[0].text.rstrip().endswith(("left,", "quarter,"))


def test_a_sixty_word_paragraph_gives_readable_cues_that_cover_all_its_text() -> None:
    text = " ".join(f"word{n}" if n % 9 else f"word{n}," for n in range(1, 61))
    cues = build_captions([paragraph("P5", text, 0.0, 24.0)])
    assert 4 <= len(cues) <= 12
    assert " ".join(" ".join(c.text.split("\n")) for c in cues) == text
    for cue in cues:
        assert all(len(line) <= MAX_LINE_CHARS for line in cue.text.split("\n"))


def test_a_word_longer_than_a_line_is_kept_whole() -> None:
    url = "https://example.com/" + "a" * 50
    cues = build_captions([paragraph("P6", f"See {url} now.", 0.0, 3.0)])
    assert any(url in cue.text.split("\n") for cue in cues)
    assert " ".join(" ".join(c.text.split("\n")) for c in cues) == f"See {url} now."


# --- Times -------------------------------------------------------------------------------------


def test_without_word_times_the_cues_share_the_paragraph_by_characters() -> None:
    text = "Short one. " + "A much longer second sentence follows it here."
    cues = build_captions([paragraph("P1", text, 10.0, 16.0)])
    assert len(cues) == 2
    assert cues[0].start == 10.0 and cues[1].end == 16.0
    share = len("Short one.") / len(text)
    assert cues[0].end == pytest.approx(10.0 + 6.0 * share, abs=0.4)
    assert cues[0].end <= cues[1].start


def test_word_times_place_each_cue_where_its_words_were_spoken() -> None:
    text = "First part here. Second part there."
    words = [(0.0, 0.3), (0.4, 0.7), (0.8, 1.1), (4.0, 4.3), (4.4, 4.7), (4.8, 5.1)]
    cues = build_captions([paragraph("P1", text, 0.0, 5.1, words)])
    assert [(c.start, c.end) for c in cues] == [(0.0, 1.1), (4.0, 5.1)]


def test_the_first_and_last_cue_take_the_start_and_end_of_the_paragraph() -> None:
    text = "One two. Three four."
    words = [(1.0, 1.2), (1.3, 1.5), (2.0, 2.2), (2.3, 2.9)]
    cues = build_captions([paragraph("P1", text, 0.8, 3.0, words)])
    assert (cues[0].start, cues[-1].end) == (0.8, 3.0)


def test_unmatched_words_are_placed_between_their_neighbours() -> None:
    text = "alpha beta gamma delta."
    words = [(0.0, 1.0), None, None, (4.0, 5.0)]
    (cue,) = build_captions([paragraph("P1", text, 0.0, 5.0, words)])
    assert (cue.start, cue.end) == (0.0, 5.0)


def test_a_split_inside_a_sentence_uses_the_times_of_the_words() -> None:
    text = "A long first half of the sentence is said quickly, then a pause, and the rest follows."
    tokens = text.split()
    words = []
    clock = 0.0
    for index in range(len(tokens)):
        if index == 10:
            clock += 3.0
        words.append((clock, clock + 0.3))
        clock += 0.35
    cues = build_captions([paragraph("P1", text, 0.0, clock, words)])
    assert len(cues) >= 2
    assert cues[0].end == pytest.approx(0.35 * 9 + 0.3, abs=1e-6)
    assert cues[1].start == pytest.approx(0.35 * 10 + 3.0, abs=1e-6)


def test_punctuation_only_and_hyphenated_tokens_keep_the_times_in_step() -> None:
    # "—" has no word of its own, "twenty-five thousand" is one word (25000), "25,000" is one.
    text = "Alpha — twenty-five thousand. Then 25,000 more people arrived."
    # alpha | 25000 | then 25000 more people arrived: 7 words
    words = [(i * 1.0, i * 1.0 + 0.9) for i in range(7)]
    cues = build_captions([paragraph("P1", text, 0.0, 8.9, words)])
    assert texts(cues) == ["Alpha — twenty-five thousand.", "Then 25,000 more people arrived."]
    assert (cues[0].start, cues[0].end) == (0.0, 1.9)
    assert (cues[1].start, cues[1].end) == (2.0, 8.9)


def test_a_hyphenated_token_that_is_two_words_keeps_the_times_of_both() -> None:
    text = "North-east people arrived."
    words = [(0.0, 0.4), (0.5, 0.9), (1.0, 1.4), (1.5, 1.9)]
    cues = build_captions([paragraph("P1", text, 0.0, 1.9, words)])
    assert texts(cues) == ["North-east people arrived."]
    assert (cues[0].start, cues[0].end) == (0.0, 1.9)


def test_a_spelled_out_number_is_timed_by_the_one_word_it_matched() -> None:
    text = "Revenue was three hundred and seventy-five million dollars. Then it fell."
    # revenue was | 375 | million | dollars | then it fell: 8 words
    words = [
        (0.0, 0.5),
        (0.6, 1.0),
        (1.2, 2.4),
        (2.5, 3.0),
        (3.1, 3.6),
        (5.0, 5.3),
        (5.4, 5.6),
        (5.7, 6.0),
    ]
    cues = build_captions([paragraph("P1", text, 0.0, 6.0, words)])
    assert texts(cues) == [
        "Revenue was three hundred and\nseventy-five million dollars.",
        "Then it fell.",
    ]
    assert (cues[0].start, cues[0].end) == (0.0, 3.6)
    assert (cues[1].start, cues[1].end) == (5.0, 6.0)


def test_cues_around_a_spelled_out_number_never_overlap() -> None:
    text = "It cost three hundred and seventy-five million dollars, said the report."
    words = [
        (0.0, 0.3),
        (0.4, 0.7),
        (1.0, 2.0),
        (2.1, 2.5),
        (2.6, 3.0),
        (3.1, 3.4),
        (3.5, 3.9),
        (4.0, 4.3),
    ]
    cues = build_captions([paragraph("P1", text, 0.0, 4.3, words)])
    for before, after in zip(cues, cues[1:], strict=False):
        assert before.end <= after.start


def test_a_cue_shorter_than_a_second_is_lengthened_into_free_time() -> None:
    text = "Yes. And then a longer sentence that fills the rest of the time."
    words = [(0.0, 0.3)] + [(3.0 + i * 0.4, 3.4 + i * 0.4) for i in range(12)]
    cues = build_captions([paragraph("P1", text, 0.0, 8.0, words)])
    assert cues[0].text == "Yes."
    assert cues[0].end - cues[0].start == pytest.approx(MIN_CUE_SECONDS)


def test_lengthening_never_runs_into_the_next_paragraph() -> None:
    first = paragraph("P1", "Yes.", 0.0, 0.2)
    second = paragraph("P2", "No.", 0.5, 0.7)
    cues = build_captions([first, second])
    assert texts(cues) == ["Yes.", "No."]
    assert cues[0].end <= cues[1].start
    assert cues[0].end == pytest.approx(0.5)


def test_the_last_cue_may_run_past_the_end_of_the_paragraph_to_reach_a_second() -> None:
    (cue,) = build_captions([paragraph("P1", "Yes.", 4.0, 4.4)])
    assert (cue.start, cue.end) == (4.0, pytest.approx(5.0))


def test_a_short_sentence_with_no_free_time_is_joined_to_its_neighbour() -> None:
    # Spread by length, "Short one." gets under a second and nothing is free around it.
    text = "Short one. A much longer second sentence follows it here."
    cues = build_captions([paragraph("P1", text, 10.0, 14.0)])
    assert texts(cues) == ["Short one. A much longer second\nsentence follows it here."]
    assert (cues[0].start, cues[0].end) == (10.0, 14.0)


def test_a_short_sentence_takes_time_from_the_next_when_the_two_cannot_share_a_cue() -> None:
    second = "The second sentence has no comma and is almost eighty characters long in total."
    cues = build_captions([paragraph("P1", "Short one. " + second, 0.0, 7.6)])
    assert [cue.text.replace("\n", " ") for cue in cues] == ["Short one.", second]
    assert cues[0].end - cues[0].start == pytest.approx(MIN_CUE_SECONDS)
    assert cues[1].start == pytest.approx(cues[0].end)
    assert cues[1].end == pytest.approx(7.6)


def test_a_paragraph_of_one_short_sentence_between_other_paragraphs_stays_short() -> None:
    cues = build_captions(
        [
            paragraph("P1", "Before.", 0.0, 2.0),
            paragraph("P2", "Yes.", 2.0, 2.4),
            paragraph("P3", "After.", 2.4, 4.0),
        ]
    )
    assert cues[1].end - cues[1].start == pytest.approx(0.4)


def test_every_cue_of_a_longer_text_lasts_at_least_a_second() -> None:
    text = (
        "Evet. Peki ya sonra? Hayır. Bu kez farklı olacak, çünkü her şey değişti. "
        "Tamam. Ve böylece başladılar, yavaş yavaş, adım adım ilerleyerek."
    )
    cues = build_captions([paragraph("P1", text, 0.0, 12.0)])
    assert all(cue.end - cue.start >= MIN_CUE_SECONDS - 1e-9 for cue in cues)
    assert " ".join(" ".join(c.text.split("\n")) for c in cues) == text


def test_a_cue_over_seven_seconds_is_split_at_the_middle_word() -> None:
    text = "one two three four five six seven eight."
    words = [(i * 1.5, i * 1.5 + 1.0) for i in range(8)]
    cues = build_captions([paragraph("P1", text, 0.0, 11.5, words)])
    assert len(cues) >= 2
    assert all(cue.end - cue.start <= MAX_CUE_SECONDS for cue in cues)
    assert " ".join(" ".join(c.text.split("\n")) for c in cues) == text


def test_cues_never_overlap_across_paragraphs() -> None:
    first = paragraph("P1", "First paragraph text.", 0.0, 2.0)
    second = paragraph("P2", "Second paragraph text.", 1.9, 4.0)
    cues = build_captions([first, second])
    assert cues[0].end <= cues[1].start


def test_a_missing_paragraph_has_no_cue() -> None:
    cues = build_captions(
        [
            paragraph("P1", "Found one.", 0.0, 2.0),
            paragraph("P2", "Lost.", None, None, status=ParagraphStatus.MISSING),
            paragraph("P3", "Found two.", 5.0, 7.0),
        ]
    )
    assert texts(cues) == ["Found one.", "Found two."]


def test_a_paragraph_without_text_has_no_cue() -> None:
    assert build_captions([paragraph("P1", "", 0.0, 2.0)]) == []


# --- The file --------------------------------------------------------------------------------


def test_the_srt_numbers_the_cues_and_separates_them_with_blank_lines() -> None:
    cues = [Cue(0.4, 3.9, "First line.\nSecond line."), Cue(5.0, 7.25, "Another cue.")]
    assert format_srt(cues) == (
        "1\n00:00:00,400 --> 00:00:03,900\nFirst line.\nSecond line.\n\n"
        "2\n00:00:05,000 --> 00:00:07,250\nAnother cue.\n"
    )


def test_an_empty_list_gives_an_empty_file() -> None:
    assert format_srt([]) == ""


def test_the_file_is_utf8_without_a_byte_order_mark(tmp_path) -> None:
    path = tmp_path / "captions.srt"
    write_srt("1\n00:00:00,000 --> 00:00:01,000\nDüşüş\n", path)
    assert path.read_bytes().startswith(b"1\n")
    assert "Düşüş".encode() in path.read_bytes()


def test_an_unwritable_file_is_an_error(tmp_path) -> None:
    from vizsync.errors import OutputError

    with pytest.raises(OutputError, match="Cannot write"):
        write_srt("x", tmp_path)
