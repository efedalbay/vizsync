"""What the rest of vizsync knows about speech recognition: a word with times."""

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class Word(BaseModel):
    """One recognized word. Times are seconds on the global timeline."""

    model_config = ConfigDict(frozen=True)

    text: str
    start: float
    end: float


class Transcriber(Protocol):
    """Turns an audio file into timed words. The speech model is only used through this."""

    def transcribe(self, audio: Path, *, language: str) -> list[Word]:
        """Return the recognized words of ``audio``, with times relative to its start."""
        ...
