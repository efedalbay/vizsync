from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vizsync.cli import app
from vizsync.errors import ScriptParseError

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE = Path(__file__).parents[2] / "examples" / "northwind-script.md"

runner = CliRunner()


@pytest.mark.parametrize("mode", ["quote", "inline"])
def test_example_script_is_valid(mode: str, plain: Callable[[str], str]) -> None:
    result = runner.invoke(app, ["check", str(EXAMPLE), "--text", mode])
    assert result.exit_code == 0
    assert plain(result.stdout).strip() == "OK: 3 chapters, 8 paragraphs"


def test_quote_is_the_default_mode(plain: Callable[[str], str]) -> None:
    quote = runner.invoke(app, ["check", str(FIXTURES / "missing_quote.md")])
    assert quote.exit_code == 1
    assert "P2 has no blockquote (use --text inline?)" in plain(quote.stderr)


def test_inline_mode_accepts_a_script_without_blockquotes(plain: Callable[[str], str]) -> None:
    path = str(FIXTURES / "missing_quote.md")
    result = runner.invoke(app, ["check", path, "--text", "inline"])
    assert result.exit_code == 0
    assert plain(result.stdout).strip() == "OK: 1 chapter, 3 paragraphs"


def test_every_problem_is_reported(plain: Callable[[str], str]) -> None:
    path = FIXTURES / "several_errors.md"
    result = runner.invoke(app, ["check", str(path)])
    assert result.exit_code == 1
    lines = plain(result.stderr).splitlines()
    assert lines[0] == f"{path} line 5: P1 has no blockquote (use --text inline?)"
    assert lines[1].startswith(f"{path} line 7: P2 has no text to align")
    assert lines[2] == f"{path} line 11: P2 is repeated (first at line 7)"
    assert lines[3].startswith(f"{path} line 15: P3 is missing a separator")
    assert lines[4] == f"4 problems found in {path}"
    assert result.stdout == ""


def test_a_single_problem_is_not_pluralised(plain: Callable[[str], str]) -> None:
    result = runner.invoke(app, ["check", str(FIXTURES / "duplicate_number.md")])
    assert result.exit_code == 1
    assert plain(result.stderr).splitlines()[-1].startswith("1 problem found in ")


def test_missing_file(tmp_path: Path, plain: Callable[[str], str]) -> None:
    missing = tmp_path / "nope.md"
    result = runner.invoke(app, ["check", str(missing)])
    assert result.exit_code == 1
    assert plain(result.stderr).strip() == f"Script file not found: {missing}"


def test_messages_are_not_read_as_markup(tmp_path: Path, plain: Callable[[str], str]) -> None:
    missing = tmp_path / "[red]x.md"
    result = runner.invoke(app, ["check", str(missing)])
    assert "[red]x.md" in plain(result.stderr)


def test_invalid_text_mode_is_a_usage_error() -> None:
    result = runner.invoke(app, ["check", str(EXAMPLE), "--text", "both"])
    assert result.exit_code == 2


def test_debug_shows_the_traceback_instead_of_a_message() -> None:
    result = runner.invoke(app, ["check", str(FIXTURES / "several_errors.md"), "--debug"])
    assert result.exit_code == 1
    assert isinstance(result.exception, ScriptParseError)


def test_unexpected_error_hides_the_traceback_without_debug(
    monkeypatch: pytest.MonkeyPatch, plain: Callable[[str], str]
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("vizsync.cli.load_script", boom)
    quiet = runner.invoke(app, ["check", str(EXAMPLE)])
    assert quiet.exit_code == 1
    assert "Unexpected error" in plain(quiet.stderr)
    assert "--debug" in plain(quiet.stderr)
    loud = runner.invoke(app, ["check", str(EXAMPLE), "--debug"])
    assert isinstance(loud.exception, RuntimeError)


def test_check_appears_in_help(plain: Callable[[str], str]) -> None:
    result = runner.invoke(app, ["--help"])
    assert "check" in plain(result.output)
