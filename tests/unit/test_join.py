import wave
from pathlib import Path

import pytest

from vizsync.audio.join import (
    TRIM_PAD_SECONDS,
    JoinEntry,
    WavFormat,
    plan_join,
    read_wav_info,
    trim_range,
    write_joined,
)
from vizsync.errors import AudioError, OutputError


def write_wav(
    path: Path, frames: int, *, rate: int = 1000, channels: int = 1, width: int = 2, fill: int = 1
) -> Path:
    """A WAV whose sample bytes grow with the frame number (from ``fill``), so slices differ."""
    data = bytearray()
    for frame in range(frames):
        value = (fill + frame) % 200 + 1
        data += bytes([value]) * (width * channels)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(bytes(data))
    return path


def frames_of(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wav:
        return wav.readframes(wav.getnframes())


def layout_of(
    tmp_path: Path,
    sizes: dict[str, int],
    chapters: dict[str, int],
    *,
    paragraph_gap: float = 0.6,
    chapter_gap: float = 1.2,
    rate: int = 1000,
    **options,
):
    files = {name: write_wav(tmp_path / f"{name}.wav", n, rate=rate) for name, n in sizes.items()}
    paragraphs = [(name, chapters[name]) for name in chapters]
    return plan_join(
        paragraphs,
        files,
        target=tmp_path / "out" / "narration.wav",
        paragraph_gap=paragraph_gap,
        chapter_gap=chapter_gap,
        **options,
    )


# --- Reading a WAV -------------------------------------------------------------------------


def test_the_format_and_length_of_a_wav_are_read(tmp_path: Path) -> None:
    path = write_wav(tmp_path / "a.wav", 123, rate=22050, channels=2, width=3)
    assert read_wav_info(path) == (WavFormat(2, 3, 22050), 123)


def test_the_format_is_described_for_messages() -> None:
    assert WavFormat(1, 2, 44100).describe() == "44100 Hz, mono, 16-bit"
    assert WavFormat(2, 3, 48000).describe() == "48000 Hz, 2 channels, 24-bit"


def test_a_file_that_is_not_a_wav_is_an_error_that_says_what_to_do(tmp_path: Path) -> None:
    path = tmp_path / "P1.mp3"
    path.write_bytes(b"ID3\x04\x00\x00" + b"\x00" * 100)
    with pytest.raises(AudioError, match="plain PCM WAV") as caught:
        read_wav_info(path)
    assert caught.value.path == path


def test_a_missing_wav_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(AudioError, match="Cannot read"):
        read_wav_info(tmp_path / "nope.wav")


# --- Where every paragraph goes ------------------------------------------------------------


def test_paragraphs_follow_each_other_with_the_gaps_between_them(tmp_path: Path) -> None:
    layout = layout_of(tmp_path, {"P1": 1000, "P2": 2000, "P3": 500}, {"P1": 0, "P2": 0, "P3": 1})
    assert [(e.paragraph_id, e.offset_frames, e.frames) for e in layout.entries] == [
        ("P1", 0, 1000),
        ("P2", 1600, 2000),  # 1000 + paragraph gap 600
        ("P3", 4800, 500),  # 1600 + 2000 + chapter gap 1200
    ]
    assert layout.total_frames == 5300
    assert layout.format == WavFormat(1, 2, 1000)
    assert layout.target == tmp_path / "out" / "narration.wav"


def test_a_missing_paragraph_has_no_gap_and_the_chapter_is_compared_with_the_last_found_one(
    tmp_path: Path,
) -> None:
    sizes = {"P1": 100, "P3": 100}
    chapters = {"P1": 0, "P2": 0, "P3": 1}
    layout = layout_of(tmp_path, sizes, chapters)
    assert [e.offset_frames for e in layout.entries] == [0, 100 + 1200]


def test_two_found_paragraphs_in_one_chapter_get_the_paragraph_gap_even_across_a_missing_one(
    tmp_path: Path,
) -> None:
    layout = layout_of(tmp_path, {"P1": 100, "P3": 100}, {"P1": 0, "P2": 0, "P3": 0})
    assert [e.offset_frames for e in layout.entries] == [0, 100 + 600]


def test_gaps_are_rounded_to_whole_frames_of_the_files_rate(tmp_path: Path) -> None:
    layout = layout_of(
        tmp_path, {"P1": 441, "P2": 441}, {"P1": 0, "P2": 0}, rate=44100, paragraph_gap=0.6
    )
    assert layout.entries[1].offset_frames == 441 + 26460
    assert layout.entries[1].offset_frames / 44100 == pytest.approx(0.61)


def test_a_gap_of_zero_lays_the_files_end_to_end(tmp_path: Path) -> None:
    layout = layout_of(
        tmp_path, {"P1": 10, "P2": 20}, {"P1": 0, "P2": 1}, paragraph_gap=0.0, chapter_gap=0.0
    )
    assert [e.offset_frames for e in layout.entries] == [0, 10]
    assert layout.total_frames == 30


def test_the_order_is_the_order_of_the_script_not_of_the_files(tmp_path: Path) -> None:
    files = {
        "P2": write_wav(tmp_path / "b.wav", 100),
        "P1": write_wav(tmp_path / "a.wav", 100),
    }
    layout = plan_join(
        [("P1", 0), ("P2", 0)],
        files,
        target=tmp_path / "n.wav",
        paragraph_gap=0.0,
        chapter_gap=0.0,
    )
    assert [e.paragraph_id for e in layout.entries] == ["P1", "P2"]
    assert layout.entries[0].source.name == "a.wav"


def test_files_of_different_formats_are_an_error_naming_both(tmp_path: Path) -> None:
    files = {
        "P1": write_wav(tmp_path / "P1.wav", 100, rate=48000),
        "P2": write_wav(tmp_path / "P2.wav", 100, rate=44100),
    }
    with pytest.raises(AudioError) as caught:
        plan_join(
            [("P1", 0), ("P2", 0)],
            files,
            target=tmp_path / "n.wav",
            paragraph_gap=0.6,
            chapter_gap=1.2,
        )
    message = str(caught.value)
    assert "P2.wav is 44100 Hz, mono, 16-bit" in message
    assert "P1.wav is 48000 Hz, mono, 16-bit" in message
    assert "one format" in message


def test_a_file_that_is_also_the_target_is_an_error(tmp_path: Path) -> None:
    target = write_wav(tmp_path / "narration.wav", 100)
    with pytest.raises(AudioError, match="would be overwritten"):
        plan_join(
            [("P1", 0)],
            {"P1": target},
            target=target,
            paragraph_gap=0.6,
            chapter_gap=1.2,
        )


# --- Trimming ------------------------------------------------------------------------------


def test_the_trim_range_keeps_a_little_silence_around_the_speech() -> None:
    first, last = trim_range(4000, 1000, (1.0, 2.0), pad=0.05)
    assert (first, last) == (950, 2050)


def test_the_trim_range_never_leaves_the_file() -> None:
    assert trim_range(4000, 1000, (0.01, 3.99), pad=0.05) == (0, 4000)


def test_the_trim_range_rounds_outwards() -> None:
    first, last = trim_range(10000, 1000, (1.0004, 2.0004), pad=0.0)
    assert (first, last) == (1000, 2001)


def test_trimmed_files_start_and_end_where_the_speech_does(tmp_path: Path) -> None:
    bounds = {"P1": (1.0, 2.0), "P2": (0.5, 1.5)}
    layout = layout_of(
        tmp_path,
        {"P1": 4000, "P2": 3000},
        {"P1": 0, "P2": 0},
        speech_bounds=lambda path: bounds[path.stem],
    )
    first, second = layout.entries
    assert (first.first_frame, first.last_frame) == (1000 - 50, 2000 + 50)
    assert (second.first_frame, second.last_frame) == (500 - 50, 1500 + 50)
    assert second.offset_frames == 1100 + 600
    assert layout.total_frames == 1100 + 600 + 1100
    assert TRIM_PAD_SECONDS == 0.05


def test_a_file_with_no_speech_is_left_whole_with_a_warning(tmp_path: Path) -> None:
    layout = layout_of(
        tmp_path, {"P1": 500, "P2": 700}, {"P1": 0, "P2": 0}, speech_bounds=lambda path: None
    )
    assert [e.frames for e in layout.entries] == [500, 700]
    assert layout.warnings == [
        "P1.wav: no speech found, not trimmed.",
        "P2.wav: no speech found, not trimmed.",
    ]


def test_without_trimming_the_files_are_whole(tmp_path: Path) -> None:
    layout = layout_of(tmp_path, {"P1": 500}, {"P1": 0})
    assert layout.entries == [JoinEntry("P1", tmp_path / "P1.wav", 0, 500, 0)]
    assert layout.warnings == []


# --- The joined file -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("channels", "width", "silence"),
    [(1, 2, 0), (2, 2, 0), (1, 3, 0), (2, 4, 0), (1, 1, 0x80)],
)
def test_the_samples_are_copied_unchanged_and_only_silence_is_added(
    tmp_path: Path, channels: int, width: int, silence: int
) -> None:
    sizes = {"P1": 30, "P2": 20, "P3": 10}
    files = {
        name: write_wav(tmp_path / f"{name}.wav", n, channels=channels, width=width, fill=i * 40)
        for i, (name, n) in enumerate(sizes.items())
    }
    layout = plan_join(
        [("P1", 0), ("P2", 0), ("P3", 1)],
        files,
        target=tmp_path / "out" / "narration.wav",
        paragraph_gap=0.006,
        chapter_gap=0.012,
    )
    write_joined(layout, layout.target)
    frame = width * channels
    data = frames_of(layout.target)
    assert len(data) == layout.total_frames * frame
    assert layout.total_frames == 30 + 6 + 20 + 12 + 10
    for entry in layout.entries:
        expected = frames_of(entry.source)[entry.first_frame * frame : entry.last_frame * frame]
        start = entry.offset_frames * frame
        assert data[start : start + len(expected)] == expected
    gap = data[30 * frame : 36 * frame]
    assert gap == bytes([silence]) * (6 * frame)
    with wave.open(str(layout.target), "rb") as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (
            channels,
            width,
            1000,
        )


def test_a_trimmed_slice_is_copied_unchanged(tmp_path: Path) -> None:
    layout = layout_of(tmp_path, {"P1": 1000}, {"P1": 0}, speech_bounds=lambda path: (0.2, 0.7))
    write_joined(layout, layout.target)
    source = frames_of(tmp_path / "P1.wav")
    assert frames_of(layout.target) == source[2 * 150 : 2 * 750]


def test_the_output_folder_is_created_and_no_temporary_file_is_left(tmp_path: Path) -> None:
    layout = layout_of(tmp_path, {"P1": 10}, {"P1": 0})
    write_joined(layout, layout.target)
    assert sorted(p.name for p in layout.target.parent.iterdir()) == ["narration.wav"]


def test_an_existing_output_is_replaced(tmp_path: Path) -> None:
    layout = layout_of(tmp_path, {"P1": 10}, {"P1": 0})
    layout.target.parent.mkdir()
    layout.target.write_bytes(b"old")
    write_joined(layout, layout.target)
    assert read_wav_info(layout.target)[1] == 10


def test_an_unwritable_output_is_an_error(tmp_path: Path) -> None:
    layout = layout_of(tmp_path, {"P1": 10}, {"P1": 0})
    (tmp_path / "out").write_text("I am a file", encoding="utf-8")
    with pytest.raises(OutputError, match="Cannot"):
        write_joined(layout, layout.target)
