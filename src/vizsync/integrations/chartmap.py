"""The chart map: which script paragraphs each vizreel chart covers.

A YAML file with ``version: 1`` and ``charts``, a mapping from a vizreel chart id to
``paragraphs`` (one or more identifiers) and an optional ``sequence: true``. Every problem is
reported at once, each naming the file and the chart.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from vizsync.errors import ChartMapError
from vizsync.script.models import ChartTag, Script

SUPPORTED_VERSION = 1
SEQUENCE_CLIPS = (2, 8)
"""The fewest and most clips vizreel allows in a sequence."""

_ID = re.compile(r"^[a-z0-9-]+$")
_WINDOWS_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])$")
_FIELDS = ("paragraphs", "sequence")


@dataclass(frozen=True)
class ChartEntry:
    """One chart: its vizreel id, the paragraphs it covers, and whether it is a sequence."""

    id: str
    paragraphs: list[str]
    sequence: bool


@dataclass(frozen=True)
class ChartMap:
    """The charts of a chart map, in the order of the file."""

    charts: list[ChartEntry]


def load_chart_map(path: Path) -> ChartMap:
    """Read and validate a chart map file.

    Raises:
        ChartMapError: If the file cannot be read or has problems.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as error:
        raise ChartMapError(f"Cannot read the chart map ({error.strerror})", path=path) from None
    except UnicodeDecodeError:
        raise ChartMapError("Cannot read the chart map (not UTF-8 text)", path=path) from None
    return parse_chart_map(text, source=path)


def parse_chart_map(text: str, *, source: Path) -> ChartMap:
    """Validate chart map text. ``source`` is only used in messages.

    Raises:
        ChartMapError: Listing every problem, one per line.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ChartMapError(f"{source}: not valid YAML ({_first_line(error)})") from None
    problems: list[str] = []
    charts = _charts(data, problems)
    if problems:
        raise ChartMapError("\n".join(f"{source}: {problem}" for problem in problems))
    return ChartMap(charts)


def chart_map_from_script(script: Script, *, source: Path) -> ChartMap:
    """Build the chart map from the ``<!-- chart: ID -->`` tags of a script.

    The paragraphs with the same chart id make one chart, in script order; ``sequence`` must be
    on every tag of a chart or on none. A script without tags gives an empty map.

    Args:
        script: The parsed script.
        source: The script file, used only to name it in messages.

    Raises:
        ChartMapError: Listing every problem, each with the line of the tag.
    """
    tagged: dict[str, list[tuple[str, ChartTag]]] = {}
    for paragraph in script.paragraphs:
        for tag in paragraph.charts:
            tagged.setdefault(tag.id, []).append((paragraph.id, tag))
    entries: list[ChartEntry] = []
    problems: list[str] = []
    for chart_id, items in tagged.items():
        first_line = items[0][1].line
        flags = [tag.sequence for _, tag in items]
        found = len(problems)
        if _WINDOWS_RESERVED.match(chart_id):
            problems.append(
                _at(source, first_line, chart_id, f"'{chart_id}' is a name Windows reserves")
            )
        if len(set(flags)) > 1:
            odd = next(tag.line for _, tag in items if tag.sequence != flags[0])
            problems.append(
                _at(
                    source,
                    odd,
                    chart_id,
                    "'sequence' must be on every paragraph of the chart or on none",
                )
            )
        elif flags[0]:
            fewest, most = SEQUENCE_CLIPS
            if not fewest <= len(items) <= most:
                problems.append(
                    _at(
                        source,
                        first_line,
                        chart_id,
                        f"a sequence needs {fewest} to {most} paragraphs, got {len(items)}",
                    )
                )
        if len(problems) == found:
            entries.append(ChartEntry(chart_id, [name for name, _ in items], flags[0]))
    if problems:
        raise ChartMapError("\n".join(problems))
    return ChartMap(entries)


def merge_chart_maps(first: ChartMap, second: ChartMap, *, names: tuple[str, str]) -> ChartMap:
    """Put two chart maps together, the charts of ``first`` before those of ``second``.

    Raises:
        ChartMapError: If a chart is in both, naming ``names``.
    """
    known = {chart.id for chart in first.charts}
    problems = [
        f"charts.{chart.id} is in both {names[0]} and {names[1]}; give each chart in one place"
        for chart in second.charts
        if chart.id in known
    ]
    problems.sort()
    if problems:
        raise ChartMapError("\n".join(problems))
    return ChartMap([*first.charts, *second.charts])


def collect_charts(
    *, map_file: Path | None, script: Script | None, script_file: Path | None
) -> ChartMap:
    """The charts of a chart map file, of the tags of a script, or of both together.

    Raises:
        ChartMapError: If a chart is in both, a source has problems, or there is no chart at all.
    """
    from_file = load_chart_map(map_file) if map_file is not None else None
    from_script = None
    if script is not None and script_file is not None:
        from_script = chart_map_from_script(script, source=script_file)
    if from_file is not None and from_script is not None and map_file and script_file:
        return merge_chart_maps(from_file, from_script, names=(map_file.name, script_file.name))
    found = from_file or from_script
    if found is None or not found.charts:
        raise ChartMapError(
            "No chart found: tag the paragraphs with <!-- chart: ID --> or give a chart map",
            path=script_file or map_file,
        )
    return found


def _at(source: Path, line: int, chart_id: str, message: str) -> str:
    return f"{source} line {line}: charts.{chart_id}: {message}"


def _charts(data: Any, problems: list[str]) -> list[ChartEntry]:
    if not isinstance(data, dict):
        problems.append("the file must hold 'version' and 'charts'")
        return []
    _check_version(data, problems)
    raw = data.get("charts")
    if not isinstance(raw, dict) or not raw:
        problems.append("charts: at least one chart is required")
        return []
    entries = [_chart(str(name), value, problems) for name, value in raw.items()]
    return [entry for entry in entries if entry is not None]


def _check_version(data: dict[Any, Any], problems: list[str]) -> None:
    if "version" not in data:
        problems.append("version is required (write 'version: 1')")
    elif data["version"] != SUPPORTED_VERSION:
        problems.append(f"version must be {SUPPORTED_VERSION}, got {data['version']}")


def _chart(name: str, value: Any, problems: list[str]) -> ChartEntry | None:
    where = f"charts.{name}"
    before = len(problems)
    if not _ID.match(name):
        problems.append(f"{where}: the id may only use a-z, 0-9 and '-'")
    elif _WINDOWS_RESERVED.match(name):
        problems.append(f"{where}: '{name}' is a name Windows reserves")
    if not isinstance(value, dict):
        problems.append(f"{where}: must have 'paragraphs' (and optionally 'sequence')")
        return None
    for field in value:
        if field not in _FIELDS:
            problems.append(f"{where}: unknown field '{field}' (use {', '.join(_FIELDS)})")
    paragraphs = _paragraphs(where, value, problems)
    sequence = _sequence(where, value, paragraphs, problems)
    if len(problems) > before or paragraphs is None:
        return None
    return ChartEntry(id=name, paragraphs=paragraphs, sequence=sequence)


def _paragraphs(where: str, value: dict[Any, Any], problems: list[str]) -> list[str] | None:
    if "paragraphs" not in value:
        problems.append(f"{where}: paragraphs is required")
        return None
    names = value["paragraphs"]
    if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
        problems.append(f"{where}.paragraphs: must be a list of paragraph identifiers")
        return None
    for name in dict.fromkeys(names):
        if names.count(name) > 1:
            problems.append(f"{where}: {name} is listed twice")
    return list(names)


def _sequence(
    where: str, value: dict[Any, Any], paragraphs: list[str] | None, problems: list[str]
) -> bool:
    flag = value.get("sequence", False)
    if not isinstance(flag, bool):
        problems.append(f"{where}.sequence: must be true or false")
        return False
    fewest, most = SEQUENCE_CLIPS
    if flag and paragraphs is not None and not fewest <= len(paragraphs) <= most:
        problems.append(
            f"{where}: a sequence needs {fewest} to {most} paragraphs, got {len(paragraphs)}"
        )
    return bool(flag)


def _first_line(error: yaml.YAMLError) -> str:
    return str(error).strip().splitlines()[0]
