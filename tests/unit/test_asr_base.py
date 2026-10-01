from pathlib import Path

import pytest
from fakes import FakeTranscriber, timed_words
from pydantic import ValidationError

from vizsync.asr.base import Transcriber, Word


def test_word_holds_text_and_times() -> None:
    word = Word(text="hello", start=1.5, end=1.9)
    assert (word.text, word.start, word.end) == ("hello", 1.5, 1.9)


def test_word_is_immutable() -> None:
    word = Word(text="hello", start=0.0, end=0.4)
    with pytest.raises(ValidationError):
        word.text = "bye"  # type: ignore[misc]


def test_fake_transcriber_returns_its_words_and_records_calls() -> None:
    words = timed_words("one two three")
    transcriber: Transcriber = FakeTranscriber(words)
    assert transcriber.transcribe(Path("a.wav"), language="en") == words
    assert transcriber.transcribe(Path("b.wav"), language="tr") == words
    assert isinstance(transcriber, FakeTranscriber)
    assert transcriber.calls == [(Path("a.wav"), "en"), (Path("b.wav"), "tr")]


def test_fake_transcriber_returns_a_copy() -> None:
    transcriber = FakeTranscriber(timed_words("one two"))
    transcriber.transcribe(Path("a.wav"), language="en").clear()
    assert len(transcriber.transcribe(Path("a.wav"), language="en")) == 2


def test_timed_words_lays_words_end_to_end() -> None:
    words = timed_words("a b c", start=1.0, word_duration=0.5, gap=0.25)
    assert [(w.text, w.start, w.end) for w in words] == [
        ("a", 1.0, 1.5),
        ("b", 1.75, 2.25),
        ("c", 2.5, 3.0),
    ]


def test_timed_words_of_empty_text() -> None:
    assert timed_words("   ") == []
