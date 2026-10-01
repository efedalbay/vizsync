"""Command line interface. Parses arguments and prints; no business logic."""

import math
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.text import Text

from vizsync import __version__
from vizsync.asr.faster_whisper import FasterWhisperTranscriber, download_size_mb
from vizsync.audio.inputs import AudioMode, expand_inputs, plan_audio
from vizsync.audio.timeline import read_duration
from vizsync.errors import ScriptParseError, VizsyncError
from vizsync.match.spans import DEFAULT_MIN_CONFIDENCE, ParagraphStatus
from vizsync.output.edl import DEFAULT_FPS, DEFAULT_TIMELINE_START, EdlSettings
from vizsync.output.files import FORMATS, prepare_outputs, write_outputs
from vizsync.pipeline import AlignmentResult, ParagraphResult, exit_code, run_alignment
from vizsync.script.models import TextMode
from vizsync.script.parser import load_script
from vizsync.timefmt import format_time

app = typer.Typer(
    name="vizsync",
    help="Find where each paragraph of a script starts and ends in a narration recording.",
    no_args_is_help=True,
    add_completion=False,
)


class Device(StrEnum):
    """Where the speech model runs."""

    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"


def _make_wrong_options_exit_with_1() -> None:
    """Make a wrong option or argument exit with code 1, as docs/SPEC.md says.

    Click uses 2 for those, but vizsync's exit code 2 means "a paragraph is missing". Typer's
    own copy of Click is not a public module, so the class is found through ``BadParameter``.
    """
    for error_class in typer.BadParameter.__mro__:
        if error_class.__name__ == "UsageError":
            error_class.exit_code = 1  # type: ignore[attr-defined]


_make_wrong_options_exit_with_1()


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"vizsync {__version__}")
        raise typer.Exit()


def _check_formats(value: str) -> str:
    unknown = [name for name in _split_formats(value) if name not in FORMATS]
    if unknown:
        raise typer.BadParameter(
            f"unknown format '{unknown[0]}' (use {', '.join(FORMATS)})", param_hint="--formats"
        )
    return value


def _split_formats(value: str) -> list[str]:
    return [name.strip().lower() for name in value.split(",") if name.strip()]


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
    # A character the console cannot show (a Turkish title in a legacy code page, say) must
    # never crash a run.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


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


@app.command()
def align(
    audio: Annotated[
        list[Path],
        typer.Argument(help="Audio files, folders or wildcards such as *.wav.", show_default=False),
    ],
    script: Annotated[Path, typer.Option("--script", "-s", help="Script file (Markdown).")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Output folder.")] = Path("out"),
    text: Annotated[
        TextMode,
        typer.Option(
            "--text",
            help="Text to align: the blockquote (quote) or the paragraph line (inline).",
        ),
    ] = TextMode.QUOTE,
    mode: Annotated[
        AudioMode,
        typer.Option("--mode", help="Recording layout: parts, per-paragraph or auto-detected."),
    ] = AudioMode.AUTO,
    model: Annotated[
        str, typer.Option("--model", help="Speech model name (tiny.en, small.en, ...) or folder.")
    ] = "small.en",
    language: Annotated[str, typer.Option("--language", help="Language of the audio.")] = "en",
    device: Annotated[Device, typer.Option("--device", help="Where the model runs.")] = Device.AUTO,
    offset: Annotated[
        float, typer.Option("--offset", min=0.0, help="Seconds added to every time.")
    ] = 0.0,
    gap: Annotated[
        float,
        typer.Option("--gap", min=0.0, help="Seconds of silence between consecutive parts."),
    ] = 0.0,
    min_confidence: Annotated[
        float,
        typer.Option(
            "--min-confidence",
            min=0.0,
            max=1.0,
            help="Below this a paragraph is reported as low confidence.",
        ),
    ] = DEFAULT_MIN_CONFIDENCE,
    strict: Annotated[
        bool, typer.Option("--strict", help="Exit with code 1 if any warning was produced.")
    ] = False,
    formats: Annotated[
        str,
        typer.Option(
            "--formats",
            callback=_check_formats,
            help="Comma-separated files to write: json, csv, chapters, edl.",
        ),
    ] = ",".join(FORMATS),
    fps: Annotated[
        float,
        typer.Option(
            "--fps",
            help="Frame rate of the video, for markers.edl: 23.976, 24, 25, 29.97, 30, 50, "
            "59.94 or 60.",
        ),
    ] = DEFAULT_FPS,
    timeline_start: Annotated[
        str,
        typer.Option(
            "--timeline-start",
            help="Timecode where the editor's timeline starts, for markers.edl "
            "(DaVinci Resolve uses 01:00:00:00).",
        ),
    ] = DEFAULT_TIMELINE_START,
    debug: Annotated[bool, typer.Option("--debug", help="Show tracebacks for errors.")] = False,
) -> None:
    """Find where each paragraph of the script is in the audio and write the result files."""
    with _handle_errors(debug):
        chosen = _split_formats(formats)
        edl = EdlSettings.parse(fps, timeline_start) if "edl" in chosen else None
        parsed = load_script(script, text)
        plan = plan_audio(expand_inputs(audio), [p.id for p in parsed.paragraphs], mode)
        transcriber = None
        if plan.mode is AudioMode.PARTS:
            transcriber = FasterWhisperTranscriber(model, device=device.value)
            if not transcriber.is_cached():
                _print(_download_notice(model), "yellow", error=True)
        with Console(stderr=True).status("Starting") as status:
            result = run_alignment(
                parsed,
                script.name,
                plan,
                transcriber=transcriber,
                language=language,
                offset=offset,
                gap=gap,
                min_confidence=min_confidence,
                read_duration=read_duration,
                on_progress=lambda message: status.update(escape(message)),
            )
        outputs = prepare_outputs(result, chosen, edl)
        _report(outputs.result)
        written = write_outputs(outputs, out, tool=f"vizsync {__version__}")
    _print("Written: " + ", ".join(str(path) for path in written), "green")
    code = exit_code(outputs.result, strict=strict)
    if code:
        raise typer.Exit(code)


def _download_notice(model: str) -> str:
    size = download_size_mb(model)
    about = f" (about {size} MB)" if size else ""
    return (
        f"Downloading the speech model '{model}'{about}. "
        "This happens once; later runs use the saved copy."
    )


def _report(result: AlignmentResult) -> None:
    for paragraph in result.paragraphs:
        Console().print(_row(paragraph), soft_wrap=True)
    for warning in result.warnings:
        _print(f"warning: {warning}", "yellow", error=True)
    counts = {status: 0 for status in ParagraphStatus}
    for paragraph in result.paragraphs:
        counts[paragraph.status] += 1
    _print(
        f"{counts[ParagraphStatus.OK]} ok, {counts[ParagraphStatus.LOW_CONFIDENCE]} low "
        f"confidence, {counts[ParagraphStatus.MISSING]} missing",
        "bold",
    )
    if result.mode is AudioMode.PARTS:
        _print(
            f"Audio {format_time(result.total_duration)}; speech recognition "
            f"{format_time(result.transcription_seconds)}; matching "
            f"{result.matching_seconds:.1f} s",
            "dim",
            error=True,
        )


def _row(paragraph: ParagraphResult) -> Text:
    label = f"{paragraph.id:<5}"
    if paragraph.start is None or paragraph.end is None:
        return Text(f"{label} (not found)  missing", style="red")
    start, end = format_time(paragraph.start), format_time(paragraph.end)
    length = f"{math.floor((paragraph.end - paragraph.start) * 10 + 0.5) / 10:.1f} s"
    row = f"{label} {start:>8} -> {end:>8}  {length:>8}  {paragraph.status.value}"
    if paragraph.status is ParagraphStatus.LOW_CONFIDENCE:
        return Text(f"{row} ({paragraph.confidence:.2f})", style="yellow")
    return Text(row)
