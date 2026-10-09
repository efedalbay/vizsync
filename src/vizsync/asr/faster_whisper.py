"""The real speech recognizer: faster-whisper behind the ``Transcriber`` interface.

The library is imported only when a model is needed, so commands that do not listen to audio
start fast.
"""

import ctypes
import logging
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

from vizsync.asr.base import Word
from vizsync.asr.snap import snap_words_to_speech
from vizsync.audio.speech import speech_segments
from vizsync.errors import ModelLoadError, TranscriptionError

MODEL_SIZES_MB = {"tiny.en": 75, "base.en": 145, "small.en": 484, "medium.en": 1500}
"""Approximate download size of the standard English models, for the message before a download."""

_COMPUTE_TYPES = {"cpu": "int8", "cuda": "float16"}

_CUDA_LIBRARIES = {
    "win32": ("cublas64_12.dll", "cudnn64_9.dll"),
    "linux": ("libcublas.so.12", "libcudnn.so.9"),
}
"""The NVIDIA libraries (cuBLAS 12, cuDNN 9) the GPU needs, which come with the CUDA toolkit."""

DEFAULT_VAD_PARAMETERS: Mapping[str, Any] = {"speech_pad_ms": 100}
"""Voice-activity options used when none are given. The library pads every stretch of speech by
400 ms, which moved paragraph starts by up to 0.6 s on the fixture clip; 100 ms gave the same
times whether the clip was recognized whole or in parts."""

ModelFactory = Callable[[str, str, str], Any]
"""``(model name or folder, device, compute type)`` to a loaded model."""

SpeechSegmentFinder = Callable[[Path], list[tuple[float, float]]]
"""An audio file to its stretches of speech, as ``(start, end)`` seconds."""


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
    """Turns audio into timed words with a faster-whisper model. Loads the model on first use.

    Word times are held to the speech the voice-activity detector finds in the same file
    (``snap_to_speech``), because the model often starts the first word after a long silence
    inside that silence.
    """

    def __init__(
        self,
        model: str = "small.en",
        *,
        device: str = "auto",
        model_factory: ModelFactory | None = None,
        vad_filter: bool = True,
        vad_parameters: Mapping[str, Any] | None = None,
        snap_to_speech: bool = True,
        speech_segments: SpeechSegmentFinder | None = None,
    ) -> None:
        self.model_name = model
        self._device = device
        self._model_factory = model_factory or _load_model
        self._vad_filter = vad_filter
        self._vad_parameters = dict(
            DEFAULT_VAD_PARAMETERS if vad_parameters is None else vad_parameters
        )
        self._snap_to_speech = snap_to_speech
        self._speech_segments = speech_segments or _default_speech_segments()
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
                str(audio),
                language=language,
                word_timestamps=True,
                vad_filter=self._vad_filter,
                vad_parameters=self._vad_parameters,
            )
            words = [
                Word(text=word.word.strip(), start=float(word.start), end=float(word.end))
                for segment in segments
                for word in segment.words or []
                if word.word.strip()
            ]
        except Exception as error:
            raise TranscriptionError(f"Speech recognition failed ({error})", path=audio) from None
        return self._held_to_speech(words, audio)

    def _held_to_speech(self, words: list[Word], audio: Path) -> list[Word]:
        """The words snapped to the speech of ``audio``, or as they are if it cannot be found."""
        if not self._snap_to_speech or not words:
            return words
        try:
            segments = self._speech_segments(audio)
        except Exception:
            return words
        return snap_words_to_speech(words, segments)

    def _loaded_model(self) -> Any:
        if self._model is None:
            device, compute_type = resolve_device(self._device, cuda_available=_cuda_usable())
            if device == "cuda" and not _cuda_libraries_load():
                raise ModelLoadError(
                    "The GPU cannot be used: the NVIDIA libraries cuBLAS 12 and cuDNN 9 could not "
                    "be loaded. Install them (see the faster-whisper documentation) or use "
                    "--device cpu."
                )
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

    # The model hub warns that anonymous downloads have lower rate limits. The models are public
    # and one download is far below any limit, so the warning would only confuse.
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    return faster_whisper


def _default_speech_segments() -> SpeechSegmentFinder:
    return speech_segments


def _load_model(name: str, device: str, compute_type: str) -> Any:
    return _library().WhisperModel(name, device=device, compute_type=compute_type)


def _cuda_usable() -> bool:
    """Whether the GPU can really be used: a device is there and its libraries load.

    A computer with an NVIDIA GPU but without cuBLAS and cuDNN reports a device, then fails
    (or hangs) the first time the model runs, so ``auto`` must not pick the GPU for it.
    """
    return _cuda_device_count() > 0 and _cuda_libraries_load()


def _cuda_device_count() -> int:
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count())
    except Exception:
        return 0


def _cuda_libraries_load() -> bool:
    names = _CUDA_LIBRARIES.get(sys.platform, ())
    if not names:
        return False
    for name in names:
        try:
            if sys.platform == "win32":
                # winmode=0 searches PATH too, where the CUDA toolkit puts its libraries.
                ctypes.WinDLL(name, winmode=0)
            else:
                ctypes.CDLL(name)
        except OSError:
            return False
    return True
