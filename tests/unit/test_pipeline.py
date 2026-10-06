from pathlib import Path

import pytest
from fakes import FakeTranscriber, timed_words

from vizsync.asr.base import Word
from vizsync.audio.inputs import AudioMode, AudioPlan, plan_audio
from vizsync.match.spans import ParagraphStatus
from vizsync.pipeline import AlignmentResult, exit_code, run_alignment
from vizsync.script.models import TextMode
from vizsync.script.parser import parse_script

SCRIPT = parse_script(
    """\
## 1. Bir / 1. One

P1 — x

> Northwind opened its first office in 2016.

P2 — x

> The team grew quickly after that.

## 2. İki / 2. Two

P3 — x

> Revenue doubled within one year.

P4 — x

> Then the biggest customer left.
""",
    TextMode.QUOTE,
)
SPOKEN = {
    "P1": "Northwind opened its first office in 2016",
    "P2": "The team grew quickly after that",
    "P3": "Revenue doubled within one year",
    "P4": "Then the biggest customer left",
}


def narration(*ids: str, start: float = 0.0, pause: float = 1.0) -> list[Word]:
    """Timed words for the given paragraphs, one after the other with a pause between them."""
    words: list[Word] = []
    clock = start
    for paragraph_id in ids:
        chunk = timed_words(SPOKEN[paragraph_id], start=clock)
        words += chunk
        clock = chunk[-1].end + pause
    return words


def durations_of(table: dict[str, float]):
    return lambda path: table[path.name]


def parts_plan(*names: str) -> AudioPlan:
    return plan_audio([Path(name) for name in names], list(SPOKEN), AudioMode.PARTS)


def run_parts(
    transcriber: FakeTranscriber, plan: AudioPlan, table: dict[str, float], **options: float
) -> AlignmentResult:
    return run_alignment(
        SCRIPT,
        "demo.md",
        plan,
        transcriber=transcriber,
        read_duration=durations_of(table),
        **options,
    )


# --- Parts mode -----------------------------------------------------------------------------


def test_one_recording_finds_every_paragraph() -> None:
    words = narration("P1", "P2", "P3", "P4")
    result = run_parts(FakeTranscriber(words), parts_plan("all.wav"), {"all.wav": 40.0})
    assert result.mode is AudioMode.PARTS
    assert [p.id for p in result.paragraphs] == ["P1", "P2", "P3", "P4"]
    assert all(p.status is ParagraphStatus.OK for p in result.paragraphs)
    assert result.paragraphs[0].start == pytest.approx(0.0)
    assert result.paragraphs[1].start > result.paragraphs[0].end
    assert result.warnings == []
    assert result.total_duration == 40.0
    assert [(part.file.name, part.offset, part.duration) for part in result.parts] == [
        ("all.wav", 0.0, 40.0)
    ]


def test_parts_are_shifted_onto_one_timeline_with_gap_and_offset() -> None:
    per_file = {
        Path("a.wav"): narration("P1", "P2"),
        Path("b.wav"): narration("P3", "P4"),
    }
    transcriber = FakeTranscriber(per_file)
    result = run_parts(
        transcriber,
        parts_plan("a.wav", "b.wav"),
        {"a.wav": 10.0, "b.wav": 8.0},
        gap=0.5,
        offset=2.0,
    )
    assert [part.offset for part in result.parts] == [2.0, 12.5]
    assert result.total_duration == pytest.approx(18.5)
    by_id = {p.id: p for p in result.paragraphs}
    local_p3 = per_file[Path("b.wav")][0].start
    assert by_id["P3"].start == pytest.approx(12.5 + local_p3)
    assert by_id["P1"].start == pytest.approx(2.0)
    assert [call[0].name for call in transcriber.calls] == ["a.wav", "b.wav"]


def test_language_is_passed_to_the_transcriber() -> None:
    transcriber = FakeTranscriber(narration("P1", "P2", "P3", "P4"))
    run_alignment(
        SCRIPT,
        "demo.md",
        parts_plan("all.wav"),
        transcriber=transcriber,
        language="tr",
        read_duration=durations_of({"all.wav": 40.0}),
    )
    assert transcriber.calls == [(Path("all.wav"), "tr")]


def test_missing_paragraph_has_no_times_and_a_warning() -> None:
    words = narration("P1", "P3", "P4")
    result = run_parts(FakeTranscriber(words), parts_plan("all.wav"), {"all.wav": 40.0})
    p2 = result.paragraphs[1]
    assert (p2.start, p2.end, p2.status) == (None, None, ParagraphStatus.MISSING)
    assert result.warnings == ["P2: not found in the audio."]
    assert exit_code(result, strict=False) == 2


def test_low_confidence_paragraph_has_a_warning_with_its_confidence() -> None:
    words = narration("P1", "P2", "P3", "P4")
    spoken_p4 = "Then the biggest customer left"
    garbled = [Word(text=w.text, start=w.start, end=w.end) for w in words]
    # Replace two of the five words of P4 with something else.
    garbled[-2] = Word(text="banana", start=garbled[-2].start, end=garbled[-2].end)
    garbled[-3] = Word(text="orange", start=garbled[-3].start, end=garbled[-3].end)
    assert len(spoken_p4.split()) == 5
    result = run_parts(FakeTranscriber(garbled), parts_plan("all.wav"), {"all.wav": 40.0})
    p4 = result.paragraphs[3]
    assert p4.status is ParagraphStatus.LOW_CONFIDENCE
    assert result.warnings == [
        f"P4: low confidence ({p4.confidence:.2f}). The narration may differ from the script."
    ]
    assert exit_code(result, strict=False) == 0
    assert exit_code(result, strict=True) == 1


def test_min_confidence_is_respected() -> None:
    words = narration("P1", "P2", "P3", "P4")
    words[-2] = Word(text="banana", start=words[-2].start, end=words[-2].end)
    strict = run_parts(
        FakeTranscriber(words), parts_plan("all.wav"), {"all.wav": 40.0}, min_confidence=0.95
    )
    relaxed = run_parts(
        FakeTranscriber(words), parts_plan("all.wav"), {"all.wav": 40.0}, min_confidence=0.5
    )
    assert strict.paragraphs[3].status is ParagraphStatus.LOW_CONFIDENCE
    assert relaxed.paragraphs[3].status is ParagraphStatus.OK


def test_chapters_span_their_found_paragraphs() -> None:
    words = narration("P1", "P2", "P3")  # P4 never spoken
    result = run_parts(FakeTranscriber(words), parts_plan("all.wav"), {"all.wav": 40.0})
    one, two = result.chapters
    assert (one.title, one.first, one.last) == ("One", "P1", "P2")
    assert one.start == result.paragraphs[0].start
    assert one.end == result.paragraphs[1].end
    assert (two.title, two.first, two.last) == ("Two", "P3", "P4")
    assert two.start == result.paragraphs[2].start
    assert two.end == result.paragraphs[2].end


def test_chapter_whose_paragraphs_are_all_missing_has_no_times() -> None:
    words = narration("P1", "P2")
    result = run_parts(FakeTranscriber(words), parts_plan("all.wav"), {"all.wav": 40.0})
    two = result.chapters[1]
    assert (two.start, two.end) == (None, None)
    assert result.warnings == ["P3: not found in the audio.", "P4: not found in the audio."]


def test_chapter_start_skips_a_missing_first_paragraph() -> None:
    words = narration("P1", "P2", "P4")
    result = run_parts(FakeTranscriber(words), parts_plan("all.wav"), {"all.wav": 40.0})
    two = result.chapters[1]
    assert two.start == result.paragraphs[3].start
    assert (two.first, two.last) == ("P3", "P4")


def test_parts_mode_needs_a_transcriber() -> None:
    with pytest.raises(ValueError, match="transcriber"):
        run_alignment(
            SCRIPT,
            "demo.md",
            parts_plan("all.wav"),
            transcriber=None,
            read_duration=durations_of({"all.wav": 1.0}),
        )


def test_progress_is_reported_per_part() -> None:
    seen: list[str] = []
    transcriber = FakeTranscriber(
        {Path("a.wav"): narration("P1", "P2"), Path("b.wav"): narration("P3", "P4")}
    )
    run_alignment(
        SCRIPT,
        "demo.md",
        parts_plan("a.wav", "b.wav"),
        transcriber=transcriber,
        read_duration=durations_of({"a.wav": 10.0, "b.wav": 10.0}),
        on_progress=seen.append,
    )
    assert any("a.wav" in message and "1/2" in message for message in seen)
    assert any("b.wav" in message and "2/2" in message for message in seen)


def test_timings_are_recorded() -> None:
    result = run_parts(
        FakeTranscriber(narration("P1", "P2", "P3", "P4")), parts_plan("a.wav"), {"a.wav": 40.0}
    )
    assert result.transcription_seconds >= 0.0
    assert result.matching_seconds >= 0.0


# --- Per-paragraph mode -------------------------------------------------------------------------


def per_paragraph_plan(*names: str) -> AudioPlan:
    return plan_audio([Path(name) for name in names], list(SPOKEN), AudioMode.PER_PARAGRAPH)


def test_per_paragraph_files_are_laid_end_to_end_in_script_order() -> None:
    plan = per_paragraph_plan("P3.wav", "P1.wav", "P2.wav", "P4.wav")
    table = {"P1.wav": 4.0, "P2.wav": 3.5, "P3.wav": 5.0, "P4.wav": 2.0}
    result = run_alignment(
        SCRIPT, "demo.md", plan, transcriber=None, read_duration=durations_of(table)
    )
    assert result.mode is AudioMode.PER_PARAGRAPH
    assert [(p.id, p.start, p.end) for p in result.paragraphs] == [
        ("P1", 0.0, 4.0),
        ("P2", 4.0, 7.5),
        ("P3", 7.5, 12.5),
        ("P4", 12.5, 14.5),
    ]
    assert all(p.status is ParagraphStatus.OK and p.confidence == 1.0 for p in result.paragraphs)
    assert result.total_duration == 14.5
    assert [part.file.name for part in result.parts] == ["P1.wav", "P2.wav", "P3.wav", "P4.wav"]
    assert result.warnings == []


def test_per_paragraph_offset_and_ignored_gap() -> None:
    plan = per_paragraph_plan("P1.wav", "P2.wav")
    table = {"P1.wav": 4.0, "P2.wav": 3.0}
    result = run_alignment(
        SCRIPT,
        "demo.md",
        plan,
        transcriber=None,
        offset=5.0,
        gap=9.0,
        read_duration=durations_of(table),
    )
    assert result.paragraphs[0].start == 5.0
    assert result.paragraphs[1].start == 9.0
    assert result.total_duration == 7.0


def test_paragraph_without_a_file_is_missing_and_takes_no_time() -> None:
    plan = per_paragraph_plan("P1.wav", "P3.wav")
    table = {"P1.wav": 4.0, "P3.wav": 3.0}
    result = run_alignment(
        SCRIPT, "demo.md", plan, transcriber=None, read_duration=durations_of(table)
    )
    by_id = {p.id: p for p in result.paragraphs}
    assert by_id["P3"].start == 4.0
    assert (by_id["P2"].start, by_id["P2"].end) == (None, None)
    assert by_id["P2"].status is ParagraphStatus.MISSING
    assert by_id["P2"].confidence == 0.0
    assert result.warnings == ["P2: no audio file.", "P4: no audio file."]
    assert exit_code(result, strict=False) == 2


def test_ignored_files_become_warnings() -> None:
    plan = per_paragraph_plan("P1.wav", "notes.wav", "P9.wav")
    table = {"P1.wav": 4.0}
    result = run_alignment(
        SCRIPT, "demo.md", plan, transcriber=None, read_duration=durations_of(table)
    )
    assert result.warnings[:2] == [
        "notes.wav: matches no paragraph of the script, ignored.",
        "P9.wav: matches no paragraph of the script, ignored.",
    ]


def test_per_paragraph_mode_never_calls_the_transcriber() -> None:
    transcriber = FakeTranscriber([])
    plan = per_paragraph_plan("P1.wav")
    run_alignment(
        SCRIPT,
        "demo.md",
        plan,
        transcriber=transcriber,
        read_duration=durations_of({"P1.wav": 1.0}),
    )
    assert transcriber.calls == []


# --- Exit codes ------------------------------------------------------------------------


def make_result(statuses: list[ParagraphStatus], warnings: list[str]) -> AlignmentResult:
    from vizsync.pipeline import ParagraphResult

    paragraphs = [
        ParagraphResult(f"P{n}", "C", 0.0, 1.0, 1.0, status) for n, status in enumerate(statuses, 1)
    ]
    return AlignmentResult(
        script_name="s.md",
        mode=AudioMode.PARTS,
        offset=0.0,
        total_duration=1.0,
        parts=[],
        chapters=[],
        paragraphs=paragraphs,
        warnings=warnings,
        transcription_seconds=0.0,
        matching_seconds=0.0,
    )


@pytest.mark.parametrize(
    ("statuses", "warnings", "strict", "expected"),
    [
        ([ParagraphStatus.OK], [], False, 0),
        ([ParagraphStatus.OK], [], True, 0),
        ([ParagraphStatus.LOW_CONFIDENCE], ["w"], False, 0),
        ([ParagraphStatus.LOW_CONFIDENCE], ["w"], True, 1),
        ([ParagraphStatus.OK, ParagraphStatus.MISSING], ["w"], False, 2),
        ([ParagraphStatus.OK, ParagraphStatus.MISSING], ["w"], True, 2),
    ],
)
def test_exit_code(
    statuses: list[ParagraphStatus], warnings: list[str], strict: bool, expected: int
) -> None:
    assert exit_code(make_result(statuses, warnings), strict=strict) == expected


# --- Paragraphs far longer than their words ---------------------------------------------------


def delayed(words: list[Word], from_index: int, seconds: float) -> list[Word]:
    """Move every word from ``from_index`` on ``seconds`` later."""
    later = [
        Word(text=w.text, start=w.start + seconds, end=w.end + seconds) for w in words[from_index:]
    ]
    return words[:from_index] + later


def test_a_paragraph_spread_over_a_long_stretch_gets_a_warning() -> None:
    # P1 has 7 words; the recognizer heard its last word 60 s after the others.
    words = delayed(narration("P1", "P2", "P3", "P4"), 6, 60.0)
    result = run_parts(FakeTranscriber(words), parts_plan("all.wav"), {"all.wav": 100.0})
    assert result.paragraphs[0].status is ParagraphStatus.OK
    assert len(result.warnings) == 1
    assert result.warnings[0].startswith("P1: 6")
    assert "for 7 words, much longer than the other paragraphs" in result.warnings[0]
    assert exit_code(result, strict=True) == 1
    assert exit_code(result, strict=False) == 0


def test_normal_narration_gets_no_slow_warning() -> None:
    words = narration("P1", "P2", "P3", "P4", pause=3.0)
    result = run_parts(FakeTranscriber(words), parts_plan("all.wav"), {"all.wav": 60.0})
    assert result.warnings == []


def test_paragraph_files_are_never_checked_for_pace() -> None:
    plan = plan_audio(
        [Path(f"P{n}.wav") for n in (1, 2, 3, 4)], list(SPOKEN), AudioMode.PER_PARAGRAPH
    )
    table = {"P1.wav": 300.0, "P2.wav": 3.0, "P3.wav": 3.0, "P4.wav": 3.0}
    result = run_alignment(
        SCRIPT, "demo.md", plan, transcriber=None, read_duration=durations_of(table)
    )
    assert result.warnings == []


# --- Joined narration -------------------------------------------------------------------------


def joined_layout(*entries: tuple[str, int, int], warnings: list[str] | None = None):
    """A layout at 1000 frames a second: ``(paragraph, offset frame, frames)``."""
    from vizsync.audio.join import JoinEntry, JoinLayout, WavFormat

    total = max((offset + frames for _, offset, frames in entries), default=0)
    return JoinLayout(
        target=Path("out/narration.wav"),
        format=WavFormat(1, 2, 1000),
        entries=[
            JoinEntry(name, Path(f"{name}.wav"), 0, frames, offset)
            for name, offset, frames in entries
        ],
        total_frames=total,
        warnings=warnings or [],
    )


def paragraph_plan(*names: str) -> AudioPlan:
    return plan_audio(
        [Path(f"{name}.wav") for name in names], list(SPOKEN), AudioMode.PER_PARAGRAPH
    )


def run_joined(layout, *names: str, **options: float) -> AlignmentResult:
    return run_alignment(
        SCRIPT, "demo.md", paragraph_plan(*names), transcriber=None, joined=layout, **options
    )


def test_joined_paragraphs_get_the_times_of_the_joined_file() -> None:
    layout = joined_layout(("P1", 0, 1000), ("P2", 1600, 2000), ("P4", 4800, 500))
    result = run_joined(layout, "P1", "P2", "P4")
    assert result.mode is AudioMode.PER_PARAGRAPH
    times = {p.id: (p.start, p.end, p.status) for p in result.paragraphs}
    assert times["P1"] == (0.0, 1.0, ParagraphStatus.OK)
    assert times["P2"] == (1.6, 3.6, ParagraphStatus.OK)
    assert times["P3"] == (None, None, ParagraphStatus.MISSING)
    assert times["P4"] == (4.8, 5.3, ParagraphStatus.OK)
    assert result.warnings == ["P3: no audio file."]


def test_a_joined_result_has_one_audio_file_and_the_length_of_the_joined_file() -> None:
    result = run_joined(joined_layout(("P1", 0, 1000), ("P2", 1600, 2000)), "P1", "P2")
    assert result.total_duration == 3.6
    assert [(part.file, part.offset, part.duration) for part in result.parts] == [
        (Path("out/narration.wav"), 0.0, 3.6)
    ]


def test_offset_shifts_a_joined_result() -> None:
    result = run_joined(joined_layout(("P1", 0, 1000), ("P2", 1600, 2000)), "P1", "P2", offset=2.0)
    assert (result.paragraphs[0].start, result.paragraphs[1].end) == (2.0, 5.6)
    assert result.total_duration == 3.6
    assert result.parts[0].offset == 2.0


def test_chapters_of_a_joined_result_follow_its_times() -> None:
    layout = joined_layout(
        ("P1", 0, 1000), ("P2", 1600, 1000), ("P3", 3800, 1000), ("P4", 5400, 1000)
    )
    result = run_joined(layout, "P1", "P2", "P3", "P4")
    assert [(c.start, c.end) for c in result.chapters] == [(0.0, 2.6), (3.8, 6.4)]


def test_trim_warnings_and_ignored_files_are_reported() -> None:
    layout = joined_layout(("P1", 0, 1000), warnings=["P1.wav: no speech found, not trimmed."])
    plan = plan_audio([Path("P1.wav"), Path("notes.wav")], list(SPOKEN), AudioMode.PER_PARAGRAPH)
    result = run_alignment(SCRIPT, "demo.md", plan, transcriber=None, joined=layout)
    assert result.warnings[:2] == [
        "notes.wav: matches no paragraph of the script, ignored.",
        "P1.wav: no speech found, not trimmed.",
    ]


def test_the_joined_narration_is_planned_from_the_script_and_the_files(tmp_path: Path) -> None:
    from fakes import write_silent_wav

    from vizsync.pipeline import plan_narration

    files = [write_silent_wav(tmp_path / f"P{n}.wav", 1.0) for n in (1, 2, 3, 4)]
    plan = plan_audio(files, list(SPOKEN), AudioMode.PER_PARAGRAPH)
    layout = plan_narration(
        SCRIPT, plan, target=tmp_path / "narration.wav", paragraph_gap=0.6, chapter_gap=1.2
    )
    rate = layout.format.frame_rate
    # P1 | 0.6 | P2 | 1.2 (new chapter) | P3 | 0.6 | P4
    assert [e.offset_frames / rate for e in layout.entries] == pytest.approx([0.0, 1.6, 3.8, 5.4])
    assert layout.total_seconds == pytest.approx(6.4)


def test_joining_needs_one_file_per_paragraph(tmp_path: Path) -> None:
    from vizsync.errors import AudioError
    from vizsync.pipeline import plan_narration

    plan = parts_plan("all.wav")
    with pytest.raises(AudioError, match="--join needs one file per paragraph"):
        plan_narration(SCRIPT, plan, target=tmp_path / "n.wav", paragraph_gap=0.6, chapter_gap=1.2)


# --- Word times and text for captions -----------------------------------------------------------


def test_every_paragraph_carries_its_text_and_the_times_of_its_words() -> None:
    words = narration("P1", "P2", "P3", "P4")
    result = run_parts(FakeTranscriber(words), parts_plan("all.wav"), {"all.wav": 40.0})
    first = result.paragraphs[0]
    assert first.text == "Northwind opened its first office in 2016."
    assert [(w.start, w.end) for w in words[:7]] == list(first.word_times)


def test_an_unmatched_script_word_has_no_time() -> None:
    words = narration("P1", "P2", "P3", "P4")
    words[1] = Word(text="banana", start=words[1].start, end=words[1].end)
    result = run_parts(FakeTranscriber(words), parts_plan("all.wav"), {"all.wav": 40.0})
    times = result.paragraphs[0].word_times
    assert times[1] is None
    assert times[0] == (words[0].start, words[0].end)
    assert len(times) == 7


def test_a_missing_paragraph_has_no_word_times() -> None:
    result = run_parts(
        FakeTranscriber(narration("P1", "P3", "P4")), parts_plan("all.wav"), {"all.wav": 40.0}
    )
    assert result.paragraphs[1].word_times == ()


def test_paragraph_files_have_text_but_no_word_times() -> None:
    plan = paragraph_plan("P1", "P2")
    result = run_alignment(
        SCRIPT,
        "demo.md",
        plan,
        transcriber=None,
        read_duration=durations_of({"P1.wav": 3.0, "P2.wav": 2.0}),
    )
    assert result.paragraphs[0].text == "Northwind opened its first office in 2016."
    assert result.paragraphs[0].word_times == ()
