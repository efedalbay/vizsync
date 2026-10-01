"""The real faster-whisper and PyAV working together, without a speech model.

A mismatch between them (PyAV 19 dropped an argument faster-whisper 1.2 still passes) only shows
when audio is decoded, so these tests decode a generated WAV and run the voice-activity filter on
it. No model is downloaded and no recording is used.
"""

from pathlib import Path

from fakes import write_silent_wav
from faster_whisper import decode_audio
from faster_whisper.vad import VadOptions, get_speech_timestamps


def test_faster_whisper_decodes_a_wav(tmp_path: Path) -> None:
    path = write_silent_wav(tmp_path / "a.wav", 1.5)
    samples = decode_audio(str(path))
    assert len(samples) == 24000


def test_voice_activity_filter_finds_no_speech_in_silence(tmp_path: Path) -> None:
    path = write_silent_wav(tmp_path / "a.wav", 2.0)
    assert get_speech_timestamps(decode_audio(str(path)), VadOptions()) == []
