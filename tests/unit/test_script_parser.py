from pathlib import Path

import pytest

from vizsync.errors import ScriptError, ScriptParseError
from vizsync.script.models import Script, TextMode
from vizsync.script.parser import clean_text, load_script, parse_script

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE = Path(__file__).parents[2] / "examples" / "northwind-script.md"


def parse(text: str, mode: TextMode = TextMode.QUOTE) -> Script:
    return parse_script(text, mode)


def problems_of(text: str, mode: TextMode = TextMode.QUOTE) -> list[tuple[int | None, str]]:
    with pytest.raises(ScriptParseError) as info:
        parse_script(text, mode)
    return [(p.line, p.message) for p in info.value.problems]


def only_paragraph_text(text: str, mode: TextMode = TextMode.INLINE) -> str:
    return parse(text, mode).paragraphs[0].text


# --- The example script -------------------------------------------------------


def test_example_quote_mode() -> None:
    script = load_script(EXAMPLE, TextMode.QUOTE)
    assert [c.title for c in script.chapters] == ["The Hook", "The Rise", "The Fall"]
    assert [p.id for p in script.paragraphs] == [f"P{n}" for n in range(1, 9)]
    assert script.paragraphs[0].text == "Northwind was worth 740 million dollars at its peak."
    assert script.paragraphs[1].text == "Then one decision changed everything."
    assert script.paragraphs[0].line == 7
    assert [len(c.paragraphs) for c in script.chapters] == [2, 3, 3]


def test_example_inline_mode() -> None:
    script = load_script(EXAMPLE, TextMode.INLINE)
    assert [c.title for c in script.chapters] == ["Kanca", "Yükseliş", "Düşüş"]
    assert script.paragraphs[0].text == "Northwind, zirvesinde 740 milyon dolar değerindeydi."
    assert script.paragraphs[1].text == "Sonra tek bir karar her şeyi değiştirdi."
    assert len(script.paragraphs) == 8


# --- Identifiers and separators ------------------------------------------------


@pytest.mark.parametrize("identifier", ["P12", "P012", "p12", "p0012"])
def test_identifier_is_normalised(identifier: str) -> None:
    paragraph = parse(f"{identifier} — Text.", TextMode.INLINE).paragraphs[0]
    assert (paragraph.id, paragraph.number) == ("P12", 12)


@pytest.mark.parametrize("separator", ["—", "–", "-", ":", "."])
@pytest.mark.parametrize("spaces", [(" ", " "), ("", " "), (" ", ""), ("", "")])
def test_every_separator_works(separator: str, spaces: tuple[str, str]) -> None:
    before, after = spaces
    assert only_paragraph_text(f"P1{before}{separator}{after}Hello there.") == "Hello there."


def test_gaps_in_numbers_are_allowed() -> None:
    script = parse("P5 — One.\n\nP7 — Two.", TextMode.INLINE)
    assert [p.id for p in script.paragraphs] == ["P5", "P7"]


def test_repeated_number_is_an_error() -> None:
    text = "P1 — One.\n\nP2 — Two.\n\nP2 — Again.\n"
    assert problems_of(text, TextMode.INLINE) == [(5, "P2 is repeated (first at line 3)")]


def test_repeated_number_that_is_not_adjacent() -> None:
    text = "P1 — One.\n\nP2 — Two.\n\nP3 — Three.\n\nP1 — Again.\n"
    assert problems_of(text, TextMode.INLINE) == [(7, "P1 is repeated (first at line 1)")]


def test_decreasing_number_is_an_error() -> None:
    text = "P1 — One.\n\nP3 — Three.\n\nP2 — Two.\n"
    assert problems_of(text, TextMode.INLINE) == [
        (5, "P2 comes after P3 but numbers must increase")
    ]


def test_identifier_without_separator_is_an_error() -> None:
    ((line, message),) = problems_of("P1 — One.\n\nP2 no separator here\n", TextMode.INLINE)
    assert line == 3
    assert message.startswith("P2 is missing a separator")


def test_word_that_only_starts_with_p_and_digits_is_text() -> None:
    assert only_paragraph_text("P1 — Peer to peer,\nP2P networks grow.") == (
        "Peer to peer, P2P networks grow."
    )


def test_identifier_must_start_the_line() -> None:
    text = "P1 — One.\n\n  P2 — indented, so not a paragraph line.\n"
    assert [p.id for p in parse(text, TextMode.INLINE).paragraphs] == ["P1"]


# --- Which text is aligned ------------------------------------------------------


def test_inline_text_continues_on_following_lines() -> None:
    assert only_paragraph_text("P1 — First line\nsecond line\nthird line.\n") == (
        "First line second line third line."
    )


def test_blank_line_ends_inline_text() -> None:
    assert only_paragraph_text("P1 — Spoken.\n\nA stray note.\n") == "Spoken."


def test_blockquote_ends_inline_text_and_is_ignored_in_inline_mode() -> None:
    assert only_paragraph_text("P1 — Spoken\n> Quote.\nmore\n") == "Spoken"


def test_heading_ends_inline_text() -> None:
    script = parse("P1 — Spoken\n#### Note\nmore\n", TextMode.INLINE)
    assert script.paragraphs[0].text == "Spoken"


def test_quote_mode_uses_only_blockquote_lines() -> None:
    text = "P1 — Türkçe metin\ndevamı\n\n> English one\n> English two.\n"
    assert only_paragraph_text(text, TextMode.QUOTE) == "English one English two."


def test_quote_lines_separated_by_blank_lines_are_joined() -> None:
    text = "P1 — Türkçe.\n\n> First.\n\n> Second.\n"
    assert only_paragraph_text(text, TextMode.QUOTE) == "First. Second."


def test_quote_marker_without_space() -> None:
    assert only_paragraph_text("P1 — Türkçe.\n\n>No space.\n", TextMode.QUOTE) == "No space."


def test_quote_mode_ignores_plain_text_after_the_quote() -> None:
    text = "P1 — Türkçe.\n\n> English.\n\nA stray note.\n"
    assert only_paragraph_text(text, TextMode.QUOTE) == "English."


def test_quote_mode_without_blockquote_is_an_error() -> None:
    text = "P1 — Türkçe.\n\n> One.\n\nP2 — İki.\n"
    assert problems_of(text) == [(5, "P2 has no blockquote (use --text inline?)")]


def test_blockquote_before_any_paragraph_is_ignored() -> None:
    script = parse("> Stray quote.\n\nP1 — Türkçe.\n\n> English.\n")
    assert script.paragraphs[0].text == "English."


def test_text_before_the_first_paragraph_is_ignored() -> None:
    script = parse("# Title\n\nSome introduction.\n\nP1 — One.\n", TextMode.INLINE)
    assert [p.text for p in script.paragraphs] == ["One."]


# --- Cleaning --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        ("It grew.[5] Then it fell.", "It grew. Then it fell."),
        ("Numbers [30][31] follow", "Numbers follow"),
        ("Cited [5]", "Cited"),
        ("A **bold** and *italic* and _under_ word", "A bold and italic and under word"),
        ("Use `code` here", "Use code here"),
        ("Hello <!-- a note --> world", "Hello world"),
        ("Before <!-- multi\nline\ncomment --> after", "Before after"),
        ("  lots   of \t space  ", "lots of space"),
        ("Keep [words in brackets] and [a5]", "Keep [words in brackets] and [a5]"),
        ("Keep 740 million and 2016's", "Keep 740 million and 2016's"),
    ],
)
def test_clean_text(raw: str, cleaned: str) -> None:
    assert clean_text(raw) == cleaned


def test_cleaning_is_applied_to_the_aligned_text() -> None:
    assert only_paragraph_text("P1 — **Big** news. [3] <!-- todo -->\n") == "Big news."


def test_cleaning_is_applied_to_quote_text() -> None:
    assert only_paragraph_text("P1 — x\n\n> _Big_ news [3]\n", TextMode.QUOTE) == "Big news"


@pytest.mark.parametrize("empty", ["[5]", "<!-- only a comment -->", "**", "[1][2] _"])
def test_empty_after_cleaning_is_an_error(empty: str) -> None:
    text = f"P1 — Metin.\n\n> {empty}\n"
    assert problems_of(text) == [(1, "P1 has no text to align (empty after cleaning)")]


def test_empty_inline_paragraph_is_an_error() -> None:
    assert problems_of("P1 —\n", TextMode.INLINE) == [
        (1, "P1 has no text to align (empty after cleaning)")
    ]


# --- Headings and chapters ---------------------------------------------------------


def test_paragraphs_before_the_first_heading_are_in_intro() -> None:
    script = parse("P1 — One.\n\n## Later\n\nP2 — Two.\n", TextMode.INLINE)
    assert [(c.title, [p.id for p in c.paragraphs]) for c in script.chapters] == [
        ("Intro", ["P1"]),
        ("Later", ["P2"]),
    ]


def test_no_intro_chapter_without_paragraphs_before_the_first_heading() -> None:
    script = parse("# Title\n\nSome text.\n\n## First\n\nP1 — One.\n", TextMode.INLINE)
    assert [c.title for c in script.chapters] == ["First"]


def test_levels_two_and_three_start_chapters() -> None:
    text = "## A\n\nP1 — One.\n\n### B\n\nP2 — Two.\n"
    assert [c.title for c in parse(text, TextMode.INLINE).chapters] == ["A", "B"]


def test_level_one_heading_is_ignored() -> None:
    text = "## A\n\nP1 — One.\n\n# Document title\n\nP2 — Two.\n"
    script = parse(text, TextMode.INLINE)
    assert [(c.title, len(c.paragraphs)) for c in script.chapters] == [("A", 2)]


def test_deeper_headings_do_not_start_chapters() -> None:
    text = "## A\n\nP1 — One.\n\n#### Detail\n\nP2 — Two.\n"
    assert [c.title for c in parse(text, TextMode.INLINE).chapters] == ["A"]


def test_paragraph_belongs_to_the_last_heading_above_it() -> None:
    text = "## A\n\nP1 — One.\n\nP2 — Two.\n\n## B\n\nP3 — Three.\n"
    script = parse(text, TextMode.INLINE)
    assert [[p.id for p in c.paragraphs] for c in script.chapters] == [["P1", "P2"], ["P3"]]


@pytest.mark.parametrize(
    ("heading", "quote_title", "inline_title"),
    [
        ("## 2. Yükseliş / 2. The Rise", "The Rise", "Yükseliş"),
        ("## Yükseliş / The Rise", "The Rise", "Yükseliş"),
        ("## A / B / C", "C", "A"),
        ("## The Rise", "The Rise", "The Rise"),
        ("## 12. The Rise", "The Rise", "The Rise"),
        ("## 2.5 million / Growth", "Growth", "2.5 million"),
        ("## Fast/Slow", "Fast/Slow", "Fast/Slow"),
        ("### Trailing spaces  ", "Trailing spaces", "Trailing spaces"),
    ],
)
def test_heading_title_rules(heading: str, quote_title: str, inline_title: str) -> None:
    text = f"{heading}\n\nP1 — Bir.\n\n> One.\n"
    assert parse(text, TextMode.QUOTE).chapters[0].title == quote_title
    assert parse(text, TextMode.INLINE).chapters[0].title == inline_title


def test_heading_without_paragraphs_is_not_a_chapter() -> None:
    text = "## Empty\n\n## Full\n\nP1 — One.\n\n## Also empty\n"
    assert [c.title for c in parse(text, TextMode.INLINE).chapters] == ["Full"]


@pytest.mark.parametrize("heading", ["##", "## ", "## 2.", "## 2. / 3."])
def test_heading_without_a_title_is_an_error(heading: str) -> None:
    assert problems_of(f"{heading}\n\nP1 — One.\n", TextMode.INLINE) == [
        (1, "chapter heading has no title")
    ]


# --- Whole-script rules --------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "\n\n", "# Title\n\nJust prose.\n", "## Chapter\n"])
def test_script_without_paragraphs_is_an_error(text: str) -> None:
    assert problems_of(text) == [(None, "no paragraphs found")]


def test_windows_line_endings_and_line_numbers() -> None:
    text = "## A\r\n\r\nP1 — One.\r\n\r\nP1 — Again.\r\n"
    assert problems_of(text, TextMode.INLINE) == [(5, "P1 is repeated (first at line 3)")]


def test_byte_order_mark_is_ignored() -> None:
    assert only_paragraph_text("﻿P1 — One.\n") == "One."


# --- Broken script fixtures ------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("missing_quote.md", [(7, "P2 has no blockquote (use --text inline?)")]),
        ("duplicate_number.md", [(11, "P2 is repeated (first at line 7)")]),
        ("decreasing_number.md", [(11, "P2 comes after P3 but numbers must increase")]),
        ("empty_after_cleaning.md", [(7, "P2 has no text to align (empty after cleaning)")]),
        (
            "several_errors.md",
            [
                (5, "P1 has no blockquote (use --text inline?)"),
                (7, "P2 has no text to align (empty after cleaning)"),
                (11, "P2 is repeated (first at line 7)"),
                (15, "P3 is missing a separator"),
            ],
        ),
    ],
)
def test_broken_fixtures(name: str, expected: list[tuple[int, str]]) -> None:
    with pytest.raises(ScriptParseError) as info:
        load_script(FIXTURES / name, TextMode.QUOTE)
    found = [(p.line, p.message) for p in info.value.problems]
    assert len(found) == len(expected)
    for (line, message), (want_line, want_message) in zip(found, expected, strict=True):
        assert line == want_line
        assert message.startswith(want_message)


def test_all_problems_are_reported_together_with_file_and_line() -> None:
    path = FIXTURES / "several_errors.md"
    with pytest.raises(ScriptParseError) as info:
        load_script(path, TextMode.QUOTE)
    lines = str(info.value).splitlines()
    assert len(lines) == 4
    assert lines[0] == f"{path} line 5: P1 has no blockquote (use --text inline?)"


def test_missing_quote_fixture_is_valid_in_inline_mode() -> None:
    assert len(load_script(FIXTURES / "missing_quote.md", TextMode.INLINE).paragraphs) == 3


# --- Loading files -----------------------------------------------------------------------


def test_load_script_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.md"
    with pytest.raises(ScriptError, match="Script file not found") as info:
        load_script(missing, TextMode.QUOTE)
    assert str(missing) in str(info.value)


def test_load_script_accepts_utf8_with_bom(tmp_path: Path) -> None:
    path = tmp_path / "bom.md"
    path.write_bytes("﻿P1 — Bir.\r\n\r\n> One.\r\n".encode())
    assert load_script(path, TextMode.QUOTE).paragraphs[0].text == "One."


def test_load_script_rejects_invalid_utf8(tmp_path: Path) -> None:
    path = tmp_path / "latin.md"
    path.write_bytes(b"P1 \x97 caf\xe9\n")
    with pytest.raises(ScriptError, match="UTF-8"):
        load_script(path, TextMode.QUOTE)


def test_load_script_on_a_directory(tmp_path: Path) -> None:
    with pytest.raises(ScriptError, match="Cannot read script file"):
        load_script(tmp_path, TextMode.QUOTE)


def test_parse_error_carries_the_path() -> None:
    with pytest.raises(ScriptParseError) as info:
        parse_script("P1 — x\n", TextMode.QUOTE, path=Path("s.md"))
    assert str(info.value) == "s.md line 1: P1 has no blockquote (use --text inline?)"


# --- Emphasised identifiers (`**P1** —`) -----------------------------------------------------


@pytest.mark.parametrize("name", ["bold", "italic", "underscore"])
def test_emphasised_identifiers_are_paragraphs_in_quote_mode(name: str) -> None:
    script = load_script(FIXTURES / f"emphasis_{name}.md", TextMode.QUOTE)
    assert [c.title for c in script.chapters] == ["The Hook", "The Fall"]
    assert [p.id for p in script.paragraphs] == ["P1", "P2", "P3"]
    assert script.paragraphs[0].text == "Northwind was worth 740 million dollars at its peak."
    assert script.paragraphs[0].line == 5


@pytest.mark.parametrize("name", ["bold", "italic", "underscore"])
def test_emphasised_identifiers_are_paragraphs_in_inline_mode(name: str) -> None:
    script = load_script(FIXTURES / f"emphasis_{name}.md", TextMode.INLINE)
    assert [c.title for c in script.chapters] == ["Kanca", "Düşüş"]
    assert script.paragraphs[0].text == "Northwind, zirvesinde 740 milyon dolar değerindeydi."


@pytest.mark.parametrize("mark", ["**", "*", "__"])
@pytest.mark.parametrize("separator", ["—", "–", "-", ":", "."])
def test_emphasised_identifiers_take_every_separator(mark: str, separator: str) -> None:
    paragraph = parse(f"{mark}p7{mark}{separator}Text.", TextMode.INLINE).paragraphs[0]
    assert (paragraph.id, paragraph.number, paragraph.text) == ("P7", 7, "Text.")


@pytest.mark.parametrize("mark", ["**", "*", "__"])
def test_emphasised_identifier_without_separator_is_an_error(mark: str) -> None:
    text = f"{mark}P1{mark} Text without a separator."
    assert problems_of(text, TextMode.INLINE) == [
        (
            1,
            "P1 is missing a separator after the identifier "
            "(use '-', ':', '.', an en dash or an em dash)",
        ),
        (None, "no paragraphs found"),
    ]


@pytest.mark.parametrize(
    "line", ["**P1* — Text.", "*P1** — Text.", "**P1__ — Text.", "_P1_ — Text."]
)
def test_mismatched_emphasis_is_not_a_paragraph_line(line: str) -> None:
    assert problems_of(line, TextMode.INLINE) == [(None, "no paragraphs found")]


def test_emphasised_and_plain_identifiers_can_be_mixed_but_numbers_stay_unique() -> None:
    text = "**P1** — One.\n\nP2 — Two.\n\n__P2__ — Again.\n"
    assert problems_of(text, TextMode.INLINE) == [(5, "P2 is repeated (first at line 3)")]


# --- Chart tags (`<!-- chart: bet-size -->`) --------------------------------------------------


def charts_of(text: str, mode: TextMode = TextMode.INLINE) -> list[list[tuple[str, bool, int]]]:
    return [[(t.id, t.sequence, t.line) for t in p.charts] for p in parse(text, mode).paragraphs]


def test_a_chart_tag_below_a_paragraph_belongs_to_it() -> None:
    text = "P1 — One.\n<!-- chart: bet-size -->\n\nP2 — Two.\n"
    assert charts_of(text) == [[("bet-size", False, 2)], []]


def test_a_chart_tag_after_a_blank_line_and_a_quote_still_belongs_to_the_paragraph() -> None:
    text = "P1 — Bir.\n\n> One.\n\n<!-- chart: bet-size -->\n\nP2 — İki.\n\n> Two.\n"
    assert charts_of(text, TextMode.QUOTE) == [[("bet-size", False, 5)], []]


def test_a_chart_tag_on_the_paragraph_line_belongs_to_that_paragraph() -> None:
    text = "P1 — One.\n\nP2 — Two. <!-- chart: bet-size -->\n"
    assert charts_of(text) == [[], [("bet-size", False, 3)]]


def test_the_tag_is_not_part_of_the_aligned_text() -> None:
    text = "P1 — One <!-- chart: a --> and\n<!-- chart: b -->\ncontinues.\n"
    paragraph = parse(text, TextMode.INLINE).paragraphs[0]
    assert paragraph.text == "One and continues."
    assert [t.id for t in paragraph.charts] == ["a", "b"]


def test_a_sequence_chart_tag_and_the_spelling_of_the_tag() -> None:
    text = (
        "P1 — One.\n<!--chart:collapse,sequence-->\n\n"
        "P2 — Two.\n<!--   CHART :  collapse ,  Sequence   -->\n"
    )
    assert charts_of(text) == [[("collapse", True, 2)], [("collapse", True, 5)]]


def test_a_paragraph_can_be_in_several_charts() -> None:
    text = "P1 — One.\n<!-- chart: a -->\n<!-- chart: b, sequence -->\n"
    assert charts_of(text) == [[("a", False, 2), ("b", True, 3)]]


def test_other_html_comments_are_left_alone() -> None:
    text = "P1 — One. <!-- TODO check -->\n<!-- chartreuse: yes -->\n"
    assert charts_of(text) == [[]]
    assert parse(text, TextMode.INLINE).paragraphs[0].text == "One."


def test_a_chart_tag_on_a_heading_or_before_any_paragraph_is_an_error() -> None:
    text = "<!-- chart: a -->\n\n## 1. Bir\n\n<!-- chart: b -->\n\nP1 — One.\n"
    assert problems_of(text, TextMode.INLINE) == [
        (1, "the chart tag is not under a paragraph"),
        (5, "the chart tag is not under a paragraph"),
    ]


def test_a_chart_tag_after_a_heading_is_not_under_the_paragraph_above() -> None:
    text = "P1 — One.\n\n## 2. Two\n<!-- chart: a -->\n\nP2 — Two.\n"
    assert problems_of(text, TextMode.INLINE) == [(4, "the chart tag is not under a paragraph")]


@pytest.mark.parametrize(
    "tag",
    ["<!-- chart: -->", "<!-- chart: , sequence -->", "<!-- chart: a, sequence, x -->"],
)
def test_a_chart_tag_with_no_usable_id_is_an_error(tag: str) -> None:
    (_, message), *_ = problems_of(f"P1 — One.\n{tag}\n", TextMode.INLINE)
    assert message.startswith("invalid chart tag")
    assert "<!-- chart: bet-size -->" in message and "sequence" in message


def test_a_chart_id_with_a_forbidden_character_is_an_error() -> None:
    assert problems_of("P1 — One.\n<!-- chart: Bet_Size -->\n", TextMode.INLINE) == [
        (2, "chart id 'Bet_Size' may only use a-z, 0-9 and '-'")
    ]


def test_an_unknown_chart_option_is_an_error() -> None:
    assert problems_of("P1 — One.\n<!-- chart: a, loop -->\n", TextMode.INLINE) == [
        (2, "unknown chart option 'loop' (the only option is 'sequence')")
    ]


def test_the_same_chart_twice_on_a_paragraph_is_an_error() -> None:
    text = "P1 — One.\n<!-- chart: a -->\n<!-- chart: a -->\n"
    assert problems_of(text, TextMode.INLINE) == [(3, "chart 'a' is tagged twice on P1")]


def test_every_chart_tag_problem_is_reported_with_the_other_problems() -> None:
    text = "P1 — One.\n<!-- chart: A -->\n\nP1 — Again.\n<!-- chart: b, x -->\n"
    assert [line for line, _ in problems_of(text, TextMode.INLINE)] == [2, 4, 5]


# --- Pause tags (`<!-- pause: 4.0 -->`) -------------------------------------------------------


def pauses_of(text: str, mode: TextMode = TextMode.INLINE) -> list[float | None]:
    return [p.pause_after for p in parse(text, mode).paragraphs]


def test_a_paragraph_without_a_pause_tag_has_no_pause() -> None:
    assert pauses_of("P1 — One.\n\nP2 — Two.\n") == [None, None]


def test_a_pause_tag_below_a_paragraph_belongs_to_it() -> None:
    text = "P1 — One.\n<!-- pause: 4.0 -->\n\nP2 — Two.\n"
    assert pauses_of(text) == [4.0, None]


def test_a_pause_tag_after_the_blockquote_still_belongs_to_the_paragraph() -> None:
    text = "P1 — Bir.\n\n> One.\n\n<!-- pause: 4 -->\n\nP2 — İki.\n\n> Two.\n"
    assert pauses_of(text, TextMode.QUOTE) == [4.0, None]


def test_the_spelling_of_the_pause_tag_is_free_and_decimals_are_read() -> None:
    assert pauses_of("P1 — One.\n<!--PAUSE:0.25-->\n\nP2 — Two.\n") == [0.25, None]


def test_a_pause_tag_is_not_part_of_the_aligned_text() -> None:
    text = "P1 — One <!-- pause: 4.0 --> two.\n\nP2 — Three.\n"
    assert parse(text, TextMode.INLINE).paragraphs[0].text == "One two."


def test_a_pause_tag_and_a_chart_tag_can_be_on_the_same_paragraph() -> None:
    text = "P1 — One.\n<!-- chart: a -->\n<!-- pause: 2 -->\n\nP2 — Two.\n"
    paragraph = parse(text, TextMode.INLINE).paragraphs[0]
    assert paragraph.pause_after == 2.0
    assert [tag.id for tag in paragraph.charts] == ["a"]


def test_a_comment_that_only_starts_like_pause_is_left_alone() -> None:
    assert pauses_of("P1 — One. <!-- pausebutton: yes -->\n\nP2 — Two.\n") == [None, None]


def test_a_pause_tag_on_a_heading_or_before_any_paragraph_is_an_error() -> None:
    text = "<!-- pause: 1 -->\n\n## 1. Bir\n\n<!-- pause: 1 -->\n\nP1 — One.\n\nP2 — Two.\n"
    assert problems_of(text, TextMode.INLINE) == [
        (1, "the pause tag is not under a paragraph"),
        (5, "the pause tag is not under a paragraph"),
    ]


@pytest.mark.parametrize(
    "content", ["", "abc", "-1", "0", "4 s", "1,5", "1.", "1e3", "nan", "inf", "1; 2"]
)
def test_a_pause_that_is_not_a_positive_number_is_an_error(content: str) -> None:
    text = f"P1 — One.\n<!-- pause: {content} -->\n\nP2 — Two.\n"
    assert problems_of(text, TextMode.INLINE) == [
        (2, "invalid pause tag (use <!-- pause: 4.0 --> with the seconds as a positive number)")
    ]


def test_two_pause_tags_on_one_paragraph_are_an_error() -> None:
    text = "P1 — One.\n<!-- pause: 1 -->\n<!-- pause: 2 -->\n\nP2 — Two.\n"
    assert problems_of(text, TextMode.INLINE) == [(3, "P1 has two pause tags (first at line 2)")]


def test_a_pause_after_the_last_paragraph_is_an_error() -> None:
    text = "P1 — One.\n\nP2 — Two.\n<!-- pause: 4 -->\n"
    assert problems_of(text, TextMode.INLINE) == [
        (4, "P2 is the last paragraph, no paragraph follows its pause")
    ]


def test_a_pause_tag_does_not_hide_other_problems() -> None:
    text = "P1 — One.\n<!-- pause: -1 -->\n\nP2 — Two.\n<!-- chart: Bad_Id -->\n"
    assert [line for line, _ in problems_of(text, TextMode.INLINE)] == [2, 5]
