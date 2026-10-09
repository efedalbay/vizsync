"""The voice-activity detector calls, with the library functions replaced by fakes."""

from pathlib import Path
from typing import Any

import faster_whisper.audio
import faster_whisper.vad
import pytest

from vizsync.audio.speech import speech_segments, vad_speech_bounds
from vizsync.errors import AudioError

RATE = 16000


class FakeVad:
    """Records what the detector is asked and answers with fixed chunks (in samples)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, chunks: list[dict[str, int]]) -> None:
        self.chunks = chunks
        self.decoded: list[tuple[str, int]] = []
        self.options: list[Any] = []
        self.rates: list[int] = []
        monkeypatch.setattr(faster_whisper.audio, "decode_audio", self.decode_audio)
        monkeypatch.setattr(faster_whisper.vad, "get_speech_timestamps", self.timestamps)

    def decode_audio(self, path: str, sampling_rate: int) -> list[float]:
        self.decoded.append((path, sampling_rate))
        return [0.0] * 10

    def timestamps(self, samples: Any, options: Any, sampling_rate: int) -> list[dict[str, int]]:
        self.options.append(options)
        self.rates.append(sampling_rate)
        return self.chunks


def fail_to_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    def decode_audio(path: str, sampling_rate: int) -> list[float]:
        raise ValueError("invalid data found")

    monkeypatch.setattr(faster_whisper.audio, "decode_audio", decode_audio)


CHUNKS = [
    {"start": 8000, "end": 40000},
    {"start": 49600, "end": 64000},
    {"start": 72000, "end": 80000},
]


def test_speech_segments_gives_every_stretch_of_speech_in_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vad = FakeVad(monkeypatch, CHUNKS)
    assert speech_segments(Path("P8.wav")) == [(0.5, 2.5), (3.1, 4.0), (4.5, 5.0)]
    assert vad.decoded == [(str(Path("P8.wav")), RATE)]
    assert vad.rates == [RATE]


def test_speech_segments_uses_narrow_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    vad = FakeVad(monkeypatch, CHUNKS)
    speech_segments(Path("P8.wav"))
    options = vad.options[0]
    assert options.speech_pad_ms == 30
    assert options.min_silence_duration_ms == 250
    assert options.min_speech_duration_ms == 100


def test_speech_segments_of_a_silent_file_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeVad(monkeypatch, [])
    assert speech_segments(Path("P8.wav")) == []


def test_speech_segments_names_a_file_it_cannot_read(monkeypatch: pytest.MonkeyPatch) -> None:
    fail_to_decode(monkeypatch)
    with pytest.raises(AudioError, match="invalid data found") as info:
        speech_segments(Path("P8.wav"))
    assert "P8.wav" in str(info.value)


def test_speech_bounds_are_the_first_start_and_the_last_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeVad(monkeypatch, CHUNKS)
    assert vad_speech_bounds(Path("P8.wav")) == (0.5, 5.0)


def test_speech_bounds_keep_their_own_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    vad = FakeVad(monkeypatch, CHUNKS)
    vad_speech_bounds(Path("P8.wav"))
    options = vad.options[0]
    assert options.speech_pad_ms == 0
    assert options.min_silence_duration_ms == 300
    assert options.min_speech_duration_ms == 100
    assert vad.rates == [RATE]


def test_speech_bounds_of_a_silent_file_are_none(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeVad(monkeypatch, [])
    assert vad_speech_bounds(Path("P8.wav")) is None


def test_speech_bounds_name_a_file_they_cannot_read(monkeypatch: pytest.MonkeyPatch) -> None:
    fail_to_decode(monkeypatch)
    with pytest.raises(AudioError) as info:
        vad_speech_bounds(Path("P8.wav"))
    assert "P8.wav" in str(info.value)
