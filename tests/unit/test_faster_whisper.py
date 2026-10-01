from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from vizsync.asr import faster_whisper as fw
from vizsync.asr.base import Word
from vizsync.errors import ModelLoadError, TranscriptionError


def fake_word(text: str, start: float, end: float) -> SimpleNamespace:
    return SimpleNamespace(word=text, start=start, end=end)


class FakeModel:
    """Stands in for ``faster_whisper.WhisperModel``."""

    def __init__(self, segments: list[SimpleNamespace], fail_with: Exception | None = None) -> None:
        self.segments = segments
        self.fail_with = fail_with
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def transcribe(self, audio: str, **options: Any) -> tuple[Any, SimpleNamespace]:
        self.calls.append((audio, options))
        if self.fail_with is not None:
            raise self.fail_with
        return iter(self.segments), SimpleNamespace(language="en")


def make_transcriber(fake: FakeModel, **kwargs: Any) -> tuple[fw.FasterWhisperTranscriber, list]:
    created: list[tuple[str, str, str]] = []

    def factory(name: str, device: str, compute_type: str) -> FakeModel:
        created.append((name, device, compute_type))
        return fake

    transcriber = fw.FasterWhisperTranscriber(
        kwargs.pop("model", "small.en"), model_factory=factory, **kwargs
    )
    return transcriber, created


# --- Device choice ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("device", "cuda", "expected"),
    [
        ("cpu", True, ("cpu", "int8")),
        ("cpu", False, ("cpu", "int8")),
        ("cuda", True, ("cuda", "float16")),
        ("cuda", False, ("cuda", "float16")),
        ("auto", True, ("cuda", "float16")),
        ("auto", False, ("cpu", "int8")),
    ],
)
def test_resolve_device(device: str, cuda: bool, expected: tuple[str, str]) -> None:
    assert fw.resolve_device(device, cuda_available=cuda) == expected


def test_unknown_device_is_an_error() -> None:
    with pytest.raises(TranscriptionError, match="device"):
        fw.resolve_device("tpu", cuda_available=False)


# --- Transcribing ------------------------------------------------------------------------------


def test_words_come_from_every_segment_with_clean_text() -> None:
    model = FakeModel(
        [
            SimpleNamespace(words=[fake_word(" Northwind", 0.5, 1.0), fake_word(" was", 1.0, 1.2)]),
            SimpleNamespace(words=[fake_word(" 740", 2.0, 2.6), fake_word("  ", 2.6, 2.7)]),
            SimpleNamespace(words=None),
        ]
    )
    transcriber, _ = make_transcriber(model)
    assert transcriber.transcribe(Path("a.wav"), language="en") == [
        Word(text="Northwind", start=0.5, end=1.0),
        Word(text="was", start=1.0, end=1.2),
        Word(text="740", start=2.0, end=2.6),
    ]


def test_transcribe_asks_for_word_times_and_voice_activity_filtering() -> None:
    model = FakeModel([])
    transcriber, _ = make_transcriber(model)
    transcriber.transcribe(Path("a.wav"), language="tr")
    audio, options = model.calls[0]
    assert audio == str(Path("a.wav"))
    assert options["language"] == "tr"
    assert options["word_timestamps"] is True
    assert options["vad_filter"] is True


def test_model_is_loaded_once_and_only_when_needed() -> None:
    model = FakeModel([])
    transcriber, created = make_transcriber(model, model="base.en", device="cpu")
    assert created == []
    transcriber.transcribe(Path("a.wav"), language="en")
    transcriber.transcribe(Path("b.wav"), language="en")
    assert created == [("base.en", "cpu", "int8")]


def test_load_failure_explains_the_download() -> None:
    def factory(name: str, device: str, compute_type: str) -> FakeModel:
        raise OSError("no route to host")

    transcriber = fw.FasterWhisperTranscriber("small.en", model_factory=factory)
    with pytest.raises(ModelLoadError) as info:
        transcriber.transcribe(Path("a.wav"), language="en")
    message = str(info.value)
    assert "small.en" in message
    assert "internet" in message
    assert "--model" in message
    assert "no route to host" in message


def test_recognition_failure_names_the_file() -> None:
    model = FakeModel([], fail_with=RuntimeError("bad stream"))
    transcriber, _ = make_transcriber(model)
    with pytest.raises(TranscriptionError, match="bad stream") as info:
        transcriber.transcribe(Path("a.wav"), language="en")
    assert "a.wav" in str(info.value)


# --- The model cache --------------------------------------------------------------------------


def fake_library(download_model: Any) -> SimpleNamespace:
    return SimpleNamespace(utils=SimpleNamespace(download_model=download_model))


def test_a_model_folder_counts_as_cached(tmp_path: Path) -> None:
    assert fw.is_model_cached(str(tmp_path)) is True


def test_cached_model_is_found_without_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def download_model(name: str, **options: Any) -> str:
        seen.update(options, name=name)
        return "/cache/model"

    monkeypatch.setattr(fw, "_library", lambda: fake_library(download_model))
    assert fw.is_model_cached("small.en") is True
    assert seen["local_files_only"] is True
    assert seen["name"] == "small.en"


def test_missing_model_is_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    def download_model(name: str, **options: Any) -> str:
        raise OSError("not in cache")

    monkeypatch.setattr(fw, "_library", lambda: fake_library(download_model))
    assert fw.is_model_cached("small.en") is False


def test_download_size_is_known_for_the_standard_models() -> None:
    assert fw.download_size_mb("tiny.en") == 75
    assert fw.download_size_mb("small.en") == 484
    assert fw.download_size_mb("/some/folder") is None
    assert fw.download_size_mb("custom-model") is None


def test_transcriber_reports_its_cache_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fw, "is_model_cached", lambda name: name == "base.en")
    assert fw.FasterWhisperTranscriber("base.en").is_cached() is True
    assert fw.FasterWhisperTranscriber("small.en").is_cached() is False
