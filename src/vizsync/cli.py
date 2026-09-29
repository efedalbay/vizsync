"""Command line interface. Parses arguments and prints; no business logic."""

import typer

from vizsync import __version__

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
