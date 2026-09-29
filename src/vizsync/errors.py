"""Expected failures. The CLI turns these into a message and exit code 1."""

from pathlib import Path


class VizsyncError(Exception):
    """Base class for every expected failure.

    The message is written for the user. When ``path`` and ``line`` are given
    they are put in front of it, so the user sees where the problem is.
    """

    def __init__(self, message: str, *, path: Path | None = None, line: int | None = None) -> None:
        self.message = message
        self.path = path
        self.line = line
        super().__init__(self._format())

    def _format(self) -> str:
        if self.path is not None and self.line is not None:
            return f"{self.path} line {self.line}: {self.message}"
        if self.path is not None:
            return f"{self.path}: {self.message}"
        if self.line is not None:
            return f"Line {self.line}: {self.message}"
        return self.message


class ScriptError(VizsyncError):
    """The script file is missing or invalid."""


class AudioError(VizsyncError):
    """An audio file is missing, unreadable or does not fit the chosen mode."""


class TranscriptionError(VizsyncError):
    """Speech recognition failed, for example the model could not be loaded."""


class ChartMapError(VizsyncError):
    """The chart map is invalid or refers to paragraphs that cannot be used."""
