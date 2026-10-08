"""Finding the audio files and telling the two recording layouts apart."""

import glob
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from vizsync.errors import AudioError

AUDIO_EXTENSIONS = frozenset(
    {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".oga", ".opus", ".aac", ".wma", ".webm", ".mp4"}
)
"""Extensions picked up from folders and wildcards. A file named in full is accepted as it is."""

_WILDCARD = re.compile(r"[*?\[]")
_DIGITS = re.compile(r"(\d+)")
_PARAGRAPH_IN_NAME = re.compile(r"(?<![A-Za-z0-9])[Pp]0*(\d+)(?!\d)")


class AudioMode(StrEnum):
    """How the audio files relate to the script."""

    AUTO = "auto"
    PARTS = "parts"
    PER_PARAGRAPH = "per-paragraph"


@dataclass(frozen=True)
class AudioPlan:
    """What to do with the audio files.

    Attributes:
        mode: ``PARTS`` or ``PER_PARAGRAPH``, never ``AUTO``.
        files: Every file given, in the order given (parts mode: playback order).
        paragraph_files: In per-paragraph mode, the file of each paragraph, in script order.
        ignored: In per-paragraph mode, files that match no paragraph of the script.
    """

    mode: AudioMode
    files: list[Path]
    paragraph_files: dict[str, Path]
    ignored: list[Path]


def natural_sort(paths: Sequence[Path]) -> list[Path]:
    """Sort so that ``part2`` comes before ``part10``, ignoring case."""
    return sorted(paths, key=lambda path: _natural_key(str(path)))


def expand_inputs(arguments: Sequence[Path]) -> list[Path]:
    """Turn files, folders and wildcards into a list of audio files.

    Wildcards are expanded here because Windows PowerShell does not do it. Files named in full
    keep the order given; the result of a folder or a wildcard is sorted naturally.

    Raises:
        AudioError: If nothing was given, a named file is missing, or a folder or wildcard
            finds no audio files.
    """
    if not arguments:
        raise AudioError("No audio files given")
    expanded: list[Path] = []
    for argument in arguments:
        expanded.extend(_expand_one(argument))
    return expanded


def paragraph_id_in_name(path: Path) -> str | None:
    """Return the paragraph identifier in a file name ("p8_take2.mp3" gives "P8"), if any.

    The identifier is ``P`` followed by digits, not glued to other letters or digits.
    """
    match = _PARAGRAPH_IN_NAME.search(path.stem)
    return f"P{int(match.group(1))}" if match else None


def plan_audio(
    files: Sequence[Path], paragraph_ids: Sequence[str], requested: AudioMode
) -> AudioPlan:
    """Decide the mode and, for per-paragraph recordings, which file belongs to which paragraph.

    Raises:
        AudioError: If two files belong to one paragraph, or per-paragraph mode finds no file
            that matches a paragraph.
    """
    files = list(files)
    known = set(paragraph_ids)
    mode = requested
    if mode is AudioMode.AUTO:
        mode = (
            AudioMode.PER_PARAGRAPH
            if _looks_like_paragraph_files(files, known)
            else AudioMode.PARTS
        )
    if mode is AudioMode.PARTS:
        return AudioPlan(AudioMode.PARTS, files, {}, [])
    by_paragraph, ignored = _assign_to_paragraphs(files, known)
    if not by_paragraph:
        raise AudioError(
            "No audio file matches a paragraph of the script "
            "(per-paragraph mode needs names like P8.wav)"
        )
    ordered = {pid: by_paragraph[pid] for pid in paragraph_ids if pid in by_paragraph}
    return AudioPlan(AudioMode.PER_PARAGRAPH, files, ordered, ignored)


def _looks_like_paragraph_files(files: Sequence[Path], known: set[str]) -> bool:
    """One file per paragraph: most names hold an identifier of the script, or all hold one."""
    if not files:
        return False
    matching = sum(paragraph_id_in_name(path) in known for path in files)
    numbered = sum(paragraph_id_in_name(path) is not None for path in files)
    return matching > 0 and (matching * 2 > len(files) or numbered == len(files))


def _assign_to_paragraphs(
    files: Sequence[Path], known: set[str]
) -> tuple[dict[str, Path], list[Path]]:
    by_paragraph: dict[str, Path] = {}
    ignored: list[Path] = []
    for path in files:
        paragraph_id = paragraph_id_in_name(path)
        if paragraph_id is None or paragraph_id not in known:
            ignored.append(path)
        elif paragraph_id in by_paragraph:
            first = by_paragraph[paragraph_id].name
            raise AudioError(f"{paragraph_id} has two audio files: {first} and {path.name}")
        else:
            by_paragraph[paragraph_id] = path
    return by_paragraph, ignored


def _natural_key(text: str) -> list[str | int]:
    return [int(part) if part.isdigit() else part.casefold() for part in _DIGITS.split(text)]


def _expand_one(argument: Path) -> list[Path]:
    if argument.is_dir():
        found = natural_sort([path for path in argument.iterdir() if _is_audio_file(path)])
        if not found:
            raise AudioError(f"No audio files found in folder: {argument}")
        return found
    if argument.exists():
        return [argument]
    if _WILDCARD.search(str(argument)):
        matches = [Path(match) for match in glob.glob(str(argument))]
        matching = natural_sort([path for path in matches if _is_audio_file(path)])
        if not matching:
            raise AudioError(f"No audio files match: {argument}")
        return matching
    raise AudioError(f"Audio file not found: {argument}")


def _is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS and path.is_file()
