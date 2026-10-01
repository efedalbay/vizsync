"""Chart clip timing for vizreel: when each clip goes on the timeline and how long it must be.

vizreel renders a chart with a fixed ``duration`` (and, for a sequence, a ``step_duration`` for
every clip after the first), and the clip is then placed on the editor's timeline. This module
turns the paragraph times of a ``timing.json`` and a chart map into those numbers. See
docs/SPEC.md section 6.

- A single clip starts with its first paragraph and lasts until its last paragraph ends, plus the
  pad.
- A sequence is cut back to back: clip *k* lasts from the start of paragraph *k* to the start of
  paragraph *k+1*, and the last clip until its paragraph ends, plus the pad.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from vizsync.errors import ChartMapError, OutputError
from vizsync.integrations.chartmap import ChartEntry, ChartMap
from vizsync.output.timing import ParagraphEntry, Timing

MIN_CLIP_SECONDS = 2.0
"""The shortest clip vizreel renders."""
SHORT_STEP_FRACTION = 0.5
"""A later clip shorter than this fraction of ``step_duration`` is reported."""


@dataclass(frozen=True)
class Clip:
    """One clip of a sequence, numbered from 1."""

    n: int
    start: float
    duration: float


@dataclass(frozen=True)
class ChartTiming:
    """Where a chart goes and how long it lasts; sequences also have a step and their clips."""

    id: str
    start: float
    duration: float
    step_duration: float | None
    clips: list[Clip]


@dataclass(frozen=True)
class ChartTimingResult:
    """The timing of every chart in the map, in the order of the map, and the warnings."""

    charts: list[ChartTiming]
    warnings: list[str]


def compute_chart_timing(
    timing: Timing, chart_map: ChartMap, *, pad: float = 0.0
) -> ChartTimingResult:
    """Work out the start and duration of every chart.

    Args:
        timing: The result of ``vizsync align``.
        chart_map: Which paragraphs each chart covers.
        pad: Seconds added to the end of a single clip, or of the last clip of a sequence.

    Raises:
        ChartMapError: Listing every chart that names an unknown or missing paragraph, or
            paragraphs that are not consecutive.
    """
    known = {p.id: p for p in timing.paragraphs}
    order = [p.id for p in timing.paragraphs]
    problems: list[str] = []
    for chart in chart_map.charts:
        problems += _problems(chart, known, order)
    if problems:
        raise ChartMapError("\n".join(problems))
    charts: list[ChartTiming] = []
    warnings: list[str] = []
    for chart in chart_map.charts:
        paragraphs = [known[name] for name in chart.paragraphs]
        warnings += _confidence_warnings(chart.id, paragraphs)
        timed = _sequence(paragraphs, pad) if chart.sequence else _single(paragraphs, pad)
        charts.append(ChartTiming(chart.id, *timed))
        warnings += _clip_warnings(chart.id, charts[-1])
    return ChartTimingResult(charts, warnings)


def format_chart_timing(result: ChartTimingResult) -> str:
    """The YAML text for ``result``, ready to be copied into a vizreel spec."""
    lines = ["charts:"]
    for chart in result.charts:
        lines += [f"  {chart.id}:", f"    start: {_number(chart.start)}"]
        lines.append(f"    duration: {_number(chart.duration)}")
        if chart.step_duration is not None:
            lines.append(f"    step_duration: {_number(chart.step_duration)}")
            lines.append("    clips:")
            lines += [
                f"      - {{ n: {clip.n}, start: {_number(clip.start)}, "
                f"duration: {_number(clip.duration)} }}"
                for clip in chart.clips
            ]
    return "\n".join(lines) + "\n"


def write_chart_timing(text: str, path: Path) -> None:
    """Write the YAML text as UTF-8.

    Raises:
        OutputError: If the file cannot be written.
    """
    try:
        with path.open("w", encoding="utf-8", newline="\n") as file:
            file.write(text)
    except OSError as error:
        raise OutputError(f"Cannot write the file ({error.strerror})", path=path) from None


def _problems(
    chart: ChartEntry, known: dict[str, ParagraphEntry], order: Sequence[str]
) -> list[str]:
    where = f"charts.{chart.id}"
    unknown = [name for name in chart.paragraphs if name not in known]
    if unknown:
        span = f"{order[0]} to {order[-1]}" if order else "no paragraphs"
        return [f"{where}: {name} is not in the timing file (it has {span})" for name in unknown]
    missing = [name for name in chart.paragraphs if known[name].start is None]
    if missing:
        return [
            f"{where}: {name} was not found in the audio, so it has no time" for name in missing
        ]
    positions = [order.index(name) for name in chart.paragraphs]
    if positions != list(range(positions[0], positions[0] + len(positions))):
        return [
            f"{where}: the paragraphs must be consecutive and in script order, "
            f"got {', '.join(chart.paragraphs)}"
        ]
    return []


def _single(
    paragraphs: Sequence[ParagraphEntry], pad: float
) -> tuple[float, float, None, list[Clip]]:
    start, end = _start(paragraphs[0]), _end(paragraphs[-1])
    return _round(start), _round(end - start + pad), None, []


def _sequence(
    paragraphs: Sequence[ParagraphEntry], pad: float
) -> tuple[float, float, float | None, list[Clip]]:
    starts = [_start(p) for p in paragraphs]
    ends = [*starts[1:], _end(paragraphs[-1]) + pad]
    clips = [
        Clip(n, _round(begin), _round(end - begin))
        for n, (begin, end) in enumerate(zip(starts, ends, strict=True), start=1)
    ]
    return clips[0].start, clips[0].duration, max(clip.duration for clip in clips[1:]), clips


def _confidence_warnings(chart_id: str, paragraphs: Sequence[ParagraphEntry]) -> list[str]:
    return [
        f"{chart_id}: {p.id} has low confidence ({p.confidence:.2f}), its time may be off."
        for p in paragraphs
        if p.status == "low_confidence"
    ]


def _clip_warnings(chart_id: str, chart: ChartTiming) -> list[str]:
    if not chart.clips:
        if chart.duration < MIN_CLIP_SECONDS:
            return [_too_short(chart_id, "the clip", chart.duration)]
        return []
    warnings = [
        _too_short(chart_id, f"clip {clip.n}", clip.duration)
        for clip in chart.clips
        if clip.duration < MIN_CLIP_SECONDS
    ]
    step = chart.step_duration or 0.0
    warnings += [
        f"{chart_id}: clip {clip.n} ({clip.duration:.1f} s) is much shorter than step_duration "
        f"({step:.1f} s); trim it in the editor."
        for clip in chart.clips[1:]
        if clip.duration < SHORT_STEP_FRACTION * step
    ]
    return warnings


def _too_short(chart_id: str, what: str, seconds: float) -> str:
    return f"{chart_id}: {what} is only {seconds:.1f} s long, vizreel needs at least 2 s."


def _start(paragraph: ParagraphEntry) -> float:
    assert paragraph.start is not None
    return paragraph.start


def _end(paragraph: ParagraphEntry) -> float:
    assert paragraph.end is not None
    return paragraph.end


def _round(value: float) -> float:
    return round(value, 3)


def _number(value: float) -> str:
    text = f"{value:.3f}".rstrip("0")
    return text + "0" if text.endswith(".") else text
