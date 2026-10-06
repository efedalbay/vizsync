"""``--trim`` with the real voice-activity detector (bundled with faster-whisper) on the fixture.

Each paragraph of the fixture clip is put between silences of different lengths, as text-to-speech
tools leave them. No speech model is needed, so these run offline.
"""

import json
import wave
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vizsync.audio.join import TRIM_PAD_SECONDS
from vizsync.audio.speech import vad_speech_bounds
from vizsync.cli import app

pytestmark = pytest.mark.slow

CLIP = Path(__file__).parents[1] / "fixtures" / "northwind.wav"
SCRIPT = Path(__file__).parents[2] / "examples" / "northwind-script.md"
# Where each paragraph is spoken in the clip (seconds), from `vizsync align` on it.
SPEECH = {"P1": (0.0, 3.6), "P2": (5.7, 7.5), "P3": (9.7, 13.0), "P4": (15.2, 17.4)}
# Silence put before and after each paragraph file.
SILENCE = {"P1": (1.0, 1.5), "P2": (0.2, 0.2), "P3": (2.0, 0.5), "P4": (0.0, 3.0)}
TOLERANCE = 0.35
"""The detector and the aligner both place a speech boundary only to within a few tenths."""


@pytest.fixture(scope="module")
def padded(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    if not CLIP.exists():
        pytest.skip(f"the fixture clip {CLIP} does not exist")
    folder = tmp_path_factory.mktemp("padded")
    files: dict[str, Path] = {}
    with wave.open(str(CLIP), "rb") as source:
        rate, width, channels = source.getframerate(), source.getsampwidth(), source.getnchannels()
        frame = width * channels
        for name, (start, end) in SPEECH.items():
            source.setpos(max(0, round((start - 0.1) * rate)))
            speech = source.readframes(round((end - start + 0.2) * rate))
            before, after = SILENCE[name]
            path = folder / f"{name}.wav"
            with wave.open(str(path), "wb") as out:
                out.setnchannels(channels)
                out.setsampwidth(width)
                out.setframerate(rate)
                out.writeframes(b"\x00" * (round(before * rate) * frame))
                out.writeframes(speech)
                out.writeframes(b"\x00" * (round(after * rate) * frame))
            files[name] = path
    return files


def test_the_detector_finds_the_speech_between_the_silences(padded: dict[str, Path]) -> None:
    for name, path in padded.items():
        start, end = SPEECH[name]
        before = SILENCE[name][0]
        found = vad_speech_bounds(path)
        assert found is not None, name
        assert found[0] == pytest.approx(before + 0.1, abs=TOLERANCE), name
        assert found[1] == pytest.approx(before + 0.1 + (end - start), abs=TOLERANCE), name


def test_a_silent_file_has_no_speech(tmp_path: Path) -> None:
    path = tmp_path / "silent.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b"\x00\x00" * 16000 * 2)
    assert vad_speech_bounds(path) is None


def test_trimmed_paragraphs_are_as_long_as_their_speech_plus_the_pad(
    padded: dict[str, Path], tmp_path: Path
) -> None:
    out = tmp_path / "out"
    result = CliRunner().invoke(
        app,
        [
            "align",
            *map(str, padded.values()),
            "--script",
            str(SCRIPT),
            "--out",
            str(out),
            "--join",
            "--trim",
        ],
    )
    assert result.exit_code == 2, result.output  # P5 to P8 have no file
    data = json.loads((out / "timing.json").read_text(encoding="utf-8"))
    for paragraph in data["paragraphs"][:4]:
        start, end = SPEECH[paragraph["id"]]
        expected = (end - start) + 2 * TRIM_PAD_SECONDS
        assert paragraph["duration"] == pytest.approx(expected, abs=2 * TOLERANCE)
    with wave.open(str(out / "narration.wav"), "rb") as joined:
        assert joined.getnframes() / joined.getframerate() == pytest.approx(
            data["total_duration"], abs=0.001
        )
