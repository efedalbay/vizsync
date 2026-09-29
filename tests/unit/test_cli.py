import re

from typer.testing import CliRunner

from vizsync import __version__
from vizsync.cli import app

runner = CliRunner()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(output: str) -> str:
    """Remove colour codes, which CI adds even though the output is not a terminal."""
    return _ANSI.sub("", output)


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert _plain(result.output).strip() == f"vizsync {__version__}"


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "--version" in _plain(result.output)


def test_no_arguments_shows_help() -> None:
    result = runner.invoke(app, [])
    assert "Usage" in _plain(result.output)
