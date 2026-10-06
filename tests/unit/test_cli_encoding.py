import os
import subprocess
import sys
from pathlib import Path

import pytest

from vizsync.cli import _make_streams_safe


class FakeStream:
    """A stream that records how it was reconfigured."""

    def __init__(self, *, terminal: bool) -> None:
        self.terminal = terminal
        self.calls: list[dict[str, str]] = []

    def isatty(self) -> bool:
        return self.terminal

    def reconfigure(self, **options: str) -> None:
        self.calls.append(options)


def test_a_terminal_keeps_its_encoding_but_never_crashes_on_a_character() -> None:
    terminal = FakeStream(terminal=True)
    _make_streams_safe([terminal])  # type: ignore[list-item]
    assert terminal.calls == [{"errors": "replace"}]


def test_output_that_is_not_a_terminal_is_written_as_utf8() -> None:
    redirected = FakeStream(terminal=False)
    _make_streams_safe([redirected])  # type: ignore[list-item]
    assert redirected.calls == [{"encoding": "utf-8", "errors": "replace"}]


def test_a_stream_that_cannot_be_reconfigured_is_left_alone() -> None:
    _make_streams_safe([object()])  # type: ignore[list-item]


@pytest.mark.parametrize("old_encoding", ["cp1254", "cp1252", "latin-1"])
def test_a_path_with_turkish_letters_reaches_a_pipe_as_utf8(
    tmp_path: Path, old_encoding: str
) -> None:
    folder = tmp_path / "ledgerfall-kitaplık"
    folder.mkdir()
    # Python on Windows writes to a pipe in the legacy code page (cp1254 on a Turkish system);
    # PYTHONIOENCODING makes any system do the same.
    env = {**os.environ, "PYTHONIOENCODING": old_encoding}
    env.pop("PYTHONUTF8", None)
    result = subprocess.run(
        [sys.executable, "-m", "vizsync", "check", str(folder / "yok.md")],
        capture_output=True,
        env=env,
        check=False,
    )
    assert result.returncode == 1
    assert "ledgerfall-kitaplık" in result.stderr.decode("utf-8")
    assert b"\xfd" not in result.stderr
