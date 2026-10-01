"""The real speech recognizer: faster-whisper behind the ``Transcriber`` interface.

The library is imported only when a model is needed, so commands that do not listen to audio
start fast.
"""

from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from vizsync.asr.base import Word
from vizsync.errors import ModelLoadError, TranscriptionError

MODEL_SIZES_MB = {"tiny.en": 75, "base.en": 145, "small.en": 484, "medium.en": 1500}
"""Approximate download size of the standard English models, for the message before a download."""

_COMPUTE_TYPES = {"cpu": "int8", "cuda": "float16"}

ModelFactory = Callable[[str, str, str], Any]
"""``(model name or folder, device, compute type)`` to a loaded model."""


def resolve_device(device: str, *, cuda_available: bool) -> tuple[str, str]:
    """Return ``(device, compute type)`` for ``auto``, ``cpu`` or ``cuda``."""
    if device == "auto":
        device = "cuda" if cuda_available else "cpu"
    if device not in _COMPUTE_TYPES:
        raise TranscriptionError(f"Unknown device '{device}' (use auto, cpu or cuda)")
    return device, _COMPUTE_TYPES[device]


def is_model_cached(model: str) -> bool:
    """Whether the model can be loaded without downloading it."""
    if Path(model).is_dir():
        return True
    try:
        _library().utils.download_model(model, local_files_only=True)
    except Exception:
        return False
    return True


def download_size_mb(model: str) -> int | None:
    """Approximate download size of a standard model, or None if unknown."""
    return MODEL_SIZES_MB.get(model)


class FasterWhisperTranscriber:
    """Turns audio into timed words with a faster-whisper model. Loads the model on first use."""

    def __init__(
        self,
        model: str = "small.en",
        *,
        device: str = "auto",
        model_factory: ModelFactory | None = None,
    ) -> None:
        self.model_name = model
        self._device = device
        self._model_factory = model_factory or _load_model
        self._model: Any = None

    def is_cached(self) -> bool:
        """Whether loading the model needs no download."""
        return is_model_cached(self.model_name)

    def transcribe(self, audio: Path, *, language: str) -> list[Word]:
        """Return the recognized words of ``audio``, with times relative to its start.

        Raises:
            ModelLoadError: If the model cannot be loaded.
            TranscriptionError: If the audio cannot be recognized.
        """
        model = self._loaded_model()
        try:
            segments, _info = model.transcribe(
                str(audio), language=language, word_timestamps=True, vad_filter=True
            )
            return [
                Word(text=word.word.strip(), start=float(word.start), end=float(word.end))
                for segment in segments
                for word in segment.words or []
                if word.word.strip()
            ]
        except Exception as error:
            raise TranscriptionError(f"Speech recognition failed ({error})", path=audio) from None

    def _loaded_model(self) -> Any:
        if self._model is None:
            device, compute_type = resolve_device(self._device, cuda_available=_cuda_available())
            try:
                self._model = self._model_factory(self.model_name, device, compute_type)
            except Exception as error:
                raise ModelLoadError(
                    f"Could not load the speech model '{self.model_name}' ({error}). "
                    "The first use downloads the model, so it needs an internet connection. "
                    "To use a model you already have, pass its folder with --model."
                ) from None
        return self._model


def _library() -> ModuleType:
    import faster_whisper

    return faster_whisper


def _load_model(name: str, device: str, compute_type: str) -> Any:
    return _library().WhisperModel(name, device=device, compute_type=compute_type)


def _cuda_available() -> bool:
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count()) > 0
    except Exception:
        return False
