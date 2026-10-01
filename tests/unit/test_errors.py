from pathlib import Path

import pytest

from vizsync.errors import (
    AudioError,
    ChartMapError,
    OutputError,
    ScriptError,
    ScriptParseError,
    ScriptProblem,
    TranscriptionError,
    VizsyncError,
)


@pytest.mark.parametrize(
    "cls", [ScriptError, AudioError, TranscriptionError, ChartMapError, OutputError]
)
def test_subclasses_are_vizsync_errors(cls: type[VizsyncError]) -> None:
    assert issubclass(cls, VizsyncError)


def test_message_only() -> None:
    assert str(VizsyncError("Something went wrong")) == "Something went wrong"


def test_message_names_file() -> None:
    err = AudioError("Audio file not found", path=Path("part3.wav"))
    assert str(err) == "part3.wav: Audio file not found"


def test_message_names_file_and_line() -> None:
    err = ScriptError("P9 has no blockquote (use --text inline?)", path=Path("script.md"), line=41)
    assert str(err) == "script.md line 41: P9 has no blockquote (use --text inline?)"


def test_line_without_path() -> None:
    err = ScriptError("P9 has no blockquote", line=41)
    assert str(err) == "Line 41: P9 has no blockquote"


def test_attributes_are_kept() -> None:
    err = ScriptError("bad", path=Path("s.md"), line=3)
    assert (err.message, err.path, err.line) == ("bad", Path("s.md"), 3)


def test_parse_error_lists_every_problem_sorted_by_line() -> None:
    problems = [ScriptProblem(11, "second"), ScriptProblem(5, "first"), ScriptProblem(None, "last")]
    err = ScriptParseError(problems, path=Path("s.md"))
    assert str(err) == "s.md line 5: first\ns.md line 11: second\ns.md: last"
    assert [p.message for p in err.problems] == ["first", "second", "last"]
    assert err.path == Path("s.md")


def test_parse_error_is_a_script_error() -> None:
    assert issubclass(ScriptParseError, ScriptError)


def test_parse_error_without_path() -> None:
    assert str(ScriptParseError([ScriptProblem(3, "bad")])) == "Line 3: bad"
