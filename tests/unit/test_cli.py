from collections.abc import Callable

from typer.testing import CliRunner

from vizsync import __version__
from vizsync.cli import app

runner = CliRunner()


def test_version(plain: Callable[[str], str]) -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert plain(result.output).strip() == f"vizsync {__version__}"


def test_help(plain: Callable[[str], str]) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "--version" in plain(result.output)


def test_no_arguments_shows_help(plain: Callable[[str], str]) -> None:
    result = runner.invoke(app, [])
    assert "Usage" in plain(result.output)
