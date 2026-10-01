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
