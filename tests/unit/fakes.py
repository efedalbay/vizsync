"""Test helpers: a transcriber that returns hand-written words, and a word builder."""

from collections.abc import Mapping, Sequence
from pathlib import Path

from vizsync.asr.base import Word


class FakeTranscriber:
    """A ``Transcriber`` that returns the words it was given and records its calls.

    Give it one list of words to return for every file, or a mapping from file to words.
    """

    def __init__(self, words: Sequence[Word] | Mapping[Path, Sequence[Word]]) -> None:
        self._words = words
        self.calls: list[tuple[Path, str]] = []

    def transcribe(self, audio: Path, *, language: str) -> list[Word]:
        self.calls.append((audio, language))
        if isinstance(self._words, Mapping):
            return list(self._words[audio])
        return list(self._words)


def timed_words(
    text: str, *, start: float = 0.0, word_duration: float = 0.4, gap: float = 0.1
) -> list[Word]:
    """Split ``text`` on whitespace and give each word a time, one after the other.

    Use it to build "recognized" words for tests. Write deliberate recognition
    mistakes straight into ``text`` ("Zoom" for "Zume").
    """
    words: list[Word] = []
    time = start
    for token in text.split():
        words.append(Word(text=token, start=round(time, 6), end=round(time + word_duration, 6)))
        time += word_duration + gap
    return words
