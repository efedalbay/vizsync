"""Expected failures. The CLI turns these into a message and exit code 1."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


def _locate(message: str, path: Path | None, line: int | None) -> str:
    """Put the file and line, when known, in front of a message."""
    if path is not None and line is not None:
        return f"{path} line {line}: {message}"
    if path is not None:
        return f"{path}: {message}"
    if line is not None:
        return f"Line {line}: {message}"
    return message


class VizsyncError(Exception):
    """Base class for every expected failure.

    The message is written for the user. When ``path`` and ``line`` are given
    they are put in front of it, so the user sees where the problem is.
    """

    def __init__(self, message: str, *, path: Path | None = None, line: int | None = None) -> None:
        self.message = message
        self.path = path
        self.line = line
        super().__init__(_locate(message, path, line))


class ScriptError(VizsyncError):
    """The script file is missing or invalid."""


@dataclass(frozen=True)
class ScriptProblem:
    """One problem found in a script. ``line`` is None when it is not tied to a line."""

    line: int | None
    message: str


class ScriptParseError(ScriptError):
    """The script has one or more problems. Every problem is listed, in line order."""

    def __init__(self, problems: Sequence[ScriptProblem], *, path: Path | None = None) -> None:
        self.problems = sorted(problems, key=lambda p: (p.line is None, p.line or 0))
        text = "\n".join(_locate(p.message, path, p.line) for p in self.problems)
        super().__init__(text)
        self.path = path


class AudioError(VizsyncError):
    """An audio file is missing, unreadable or does not fit the chosen mode."""


class TranscriptionError(VizsyncError):
    """Speech recognition failed."""


class ModelLoadError(TranscriptionError):
    """The speech model could not be loaded, for example because it could not be downloaded."""


class ChartMapError(VizsyncError):
    """The chart map is invalid or refers to paragraphs that cannot be used."""


class OutputError(VizsyncError):
    """An output file could not be written."""
