"""Command line interface. Parses arguments and prints; no business logic."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.text import Text

from vizsync import __version__
from vizsync.errors import ScriptParseError, VizsyncError
from vizsync.script.models import TextMode
from vizsync.script.parser import load_script

app = typer.Typer(
    name="vizsync",
    help="Find where each paragraph of a script starts and ends in a narration recording.",
    no_args_is_help=True,
    add_completion=False,
)


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"vizsync {__version__}")
        raise typer.Exit()


def _print(message: str, style: str, *, error: bool = False) -> None:
    Console(stderr=error).print(Text(message, style=style), soft_wrap=True)


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


@contextmanager
def _handle_errors(debug: bool) -> Iterator[None]:
    """Turn expected errors into a message and exit code 1. Tracebacks only with --debug."""
    try:
        yield
    except typer.Exit:
        raise
    except VizsyncError as error:
        if debug:
            raise
        _print(str(error), "red", error=True)
        if isinstance(error, ScriptParseError):
            where = f" in {error.path}" if error.path is not None else ""
            found = f"{_count(len(error.problems), 'problem')} found{where}"
            _print(found, "red bold", error=True)
        raise typer.Exit(1) from None
    except Exception as error:
        if debug:
            raise
        _print(
            f"Unexpected error: {error!r}. Run again with --debug for details.", "red", error=True
        )
        raise typer.Exit(1) from None


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_show_version,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Find where each paragraph of a script starts and ends in a narration recording."""


@app.command()
def check(
    script: Annotated[Path, typer.Argument(help="Script file (Markdown).")],
    text: Annotated[
        TextMode,
        typer.Option(
            "--text",
            help="Text to align: the blockquote (quote) or the paragraph line (inline).",
        ),
    ] = TextMode.QUOTE,
    debug: Annotated[bool, typer.Option("--debug", help="Show tracebacks for errors.")] = False,
) -> None:
    """Check a script and report every problem. Needs no audio and no model."""
    with _handle_errors(debug):
        parsed = load_script(script, text)
    chapters = _count(len(parsed.chapters), "chapter")
    paragraphs = _count(len(parsed.paragraphs), "paragraph")
    _print(f"OK: {chapters}, {paragraphs}", "green")
