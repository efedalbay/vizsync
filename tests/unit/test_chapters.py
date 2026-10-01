from vizsync.output.chapters import build_chapters
from vizsync.pipeline import ChapterResult


def chapter(title: str, start: float | None, end: float | None = None) -> ChapterResult:
    stop = None if start is None else (end if end is not None else start + 20)
    return ChapterResult(title=title, first="P1", last="P2", start=start, end=stop)


THREE = [chapter("The Hook", 0.4), chapter("The Rise", 21.1), chapter("The Fall", 62.9)]


def test_one_line_per_chapter_with_whole_seconds_rounded_down() -> None:
    result = build_chapters(THREE, video_end=90.0)
    assert result.lines == ["00:00 The Hook", "00:21 The Rise", "01:02 The Fall"]
    assert result.warnings == []


def test_a_time_just_below_a_second_is_not_rounded_up() -> None:
    chapters = [chapter("A", 0.0), chapter("B", 20.999), chapter("C", 45.0)]
    assert build_chapters(chapters, video_end=60.0).lines[1] == "00:20 B"


def test_the_first_chapter_is_written_at_zero_even_if_the_narration_starts_later() -> None:
    chapters = [chapter("A", 4.2), chapter("B", 25.0), chapter("C", 50.0)]
    result = build_chapters(chapters, video_end=80.0)
    assert result.lines[0] == "00:00 A"
    assert result.warnings == [
        "chapters: 'A' starts at 00:04 but YouTube needs the first chapter at 00:00; "
        "it is written at 00:00."
    ]


def test_a_first_chapter_starting_within_one_second_gives_no_warning() -> None:
    chapters = [chapter("A", 1.0), chapter("B", 25.0), chapter("C", 50.0)]
    assert build_chapters(chapters, video_end=80.0).warnings == []


def test_a_chapter_without_a_found_paragraph_is_skipped_with_a_warning() -> None:
    chapters = [chapter("A", 0.0), chapter("B", None), chapter("C", 30.0), chapter("D", 60.0)]
    result = build_chapters(chapters, video_end=90.0)
    assert result.lines == ["00:00 A", "00:30 C", "01:00 D"]
    assert result.warnings == ["chapters: 'B' skipped, none of its paragraphs was found."]


def test_when_the_first_chapter_is_skipped_the_next_one_is_written_at_zero() -> None:
    chapters = [chapter("A", None), chapter("B", 12.0), chapter("C", 40.0), chapter("D", 70.0)]
    result = build_chapters(chapters, video_end=100.0)
    assert result.lines[0] == "00:00 B"
    assert any("'B' starts at 00:12" in warning for warning in result.warnings)


def test_fewer_than_three_chapters_gives_a_warning() -> None:
    result = build_chapters([chapter("A", 0.0), chapter("B", 30.0)], video_end=60.0)
    assert result.warnings == ["chapters: only 2 chapters, YouTube needs at least 3."]
    one = build_chapters([chapter("A", 0.0)], video_end=60.0)
    assert one.warnings == ["chapters: only 1 chapter, YouTube needs at least 3."]


def test_a_chapter_shorter_than_ten_seconds_gives_a_warning() -> None:
    chapters = [chapter("A", 0.0), chapter("B", 6.0), chapter("C", 40.0)]
    result = build_chapters(chapters, video_end=80.0)
    assert result.warnings == ["chapters: 'A' is only 6 s long, YouTube needs at least 10 s."]


def test_the_last_chapter_runs_to_the_end_of_the_video() -> None:
    chapters = [chapter("A", 0.0), chapter("B", 20.0), chapter("C", 45.0)]
    result = build_chapters(chapters, video_end=52.0)
    assert result.warnings == ["chapters: 'C' is only 7 s long, YouTube needs at least 10 s."]


def test_ten_seconds_exactly_is_long_enough() -> None:
    chapters = [chapter("A", 0.0), chapter("B", 10.0), chapter("C", 25.0)]
    assert build_chapters(chapters, video_end=40.0).warnings == []


def test_a_video_of_an_hour_or_more_uses_hours_on_every_line() -> None:
    chapters = [chapter("A", 0.0), chapter("B", 1250.0), chapter("C", 3700.0)]
    result = build_chapters(chapters, video_end=3900.0)
    assert result.lines == ["0:00:00 A", "0:20:50 B", "1:01:40 C"]


def test_no_found_chapter_writes_nothing() -> None:
    result = build_chapters([chapter("A", None), chapter("B", None)], video_end=60.0)
    assert result.lines == []
    assert result.warnings[-1] == "chapters: no chapter was found, chapters.txt is not written."


def test_titles_are_written_as_given() -> None:
    chapters = [chapter("Düşüş & Fall", 0.0), chapter("B", 20.0), chapter("C", 40.0)]
    assert build_chapters(chapters, video_end=60.0).lines[0] == "00:00 Düşüş & Fall"
