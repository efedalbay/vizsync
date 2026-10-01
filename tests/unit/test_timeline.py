import wave
from pathlib import Path

import av
import pytest

from vizsync.audio.timeline import (
    Part,
    _decoded_duration,
    build_timeline,
    read_duration,
    total_duration,
)
from vizsync.errors import AudioError


def write_silent_wav(path: Path, seconds: float, rate: int = 16000) -> Path:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * round(seconds * rate))
    return path


# --- Timeline arithmetic ---------------------------------------------------------------


def test_parts_follow_each_other() -> None:
    files = [Path("a.wav"), Path("b.wav"), Path("c.wav")]
    parts = build_timeline(files, [10.0, 20.0, 5.0])
    assert parts == [
        Part(Path("a.wav"), 0.0, 10.0),
        Part(Path("b.wav"), 10.0, 20.0),
        Part(Path("c.wav"), 30.0, 5.0),
    ]


def test_gap_is_added_between_parts_only() -> None:
    parts = build_timeline([Path("a.wav"), Path("b.wav"), Path("c.wav")], [10, 20, 5], gap=0.5)
    assert [part.offset for part in parts] == [0.0, 10.5, 31.0]


def test_offset_shifts_every_part() -> None:
    parts = build_timeline([Path("a.wav"), Path("b.wav")], [10, 20], gap=1.0, offset=5.0)
    assert [part.offset for part in parts] == [5.0, 16.0]


def test_single_part() -> None:
    assert build_timeline([Path("a.wav")], [12.5]) == [Part(Path("a.wav"), 0.0, 12.5)]


def test_no_files_gives_an_empty_timeline() -> None:
    assert build_timeline([], []) == []


def test_files_and_durations_must_pair_up() -> None:
    with pytest.raises(ValueError, match="one duration per file"):
        build_timeline([Path("a.wav")], [1.0, 2.0])


def test_total_duration_includes_the_gaps_but_not_the_offset() -> None:
    assert total_duration([10.0, 20.0, 5.0], gap=0.5) == pytest.approx(36.0)
    assert total_duration([10.0], gap=3.0) == 10.0
    assert total_duration([], gap=1.0) == 0.0


# --- Reading durations (a generated silent WAV, no recording, no model) ---------------------


def test_read_duration_of_a_wav(tmp_path: Path) -> None:
    path = write_silent_wav(tmp_path / "a.wav", 0.5)
    assert read_duration(path) == pytest.approx(0.5, abs=0.01)


def test_read_duration_at_another_sample_rate(tmp_path: Path) -> None:
    path = write_silent_wav(tmp_path / "a.wav", 1.25, rate=44100)
    assert read_duration(path) == pytest.approx(1.25, abs=0.01)


def test_duration_can_be_counted_from_the_decoded_samples(tmp_path: Path) -> None:
    path = write_silent_wav(tmp_path / "a.wav", 0.75)
    with av.open(str(path)) as container:
        assert _decoded_duration(container) == pytest.approx(0.75, abs=0.01)


def test_read_duration_of_a_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.wav"
    with pytest.raises(AudioError) as info:
        read_duration(missing)
    assert str(missing) in str(info.value)


def test_read_duration_of_a_file_that_is_not_audio(tmp_path: Path) -> None:
    path = tmp_path / "notes.wav"
    path.write_text("this is not audio", encoding="utf-8")
    with pytest.raises(AudioError, match="Cannot read audio") as info:
        read_duration(path)
    assert str(path) in str(info.value)
