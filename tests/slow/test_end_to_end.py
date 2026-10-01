"""End-to-end checks with the real speech model on the fixture clip.

These need the clip ``tests/fixtures/northwind.wav`` (a PCM WAV of the English lines of
``examples/northwind-script.md``, with pauses of at least 0.8 s between paragraphs) and a speech
model. They are skipped, with the reason, when either is missing. Run them with
``uv run pytest -m slow -rs``. ``VIZSYNC_TEST_MODEL`` picks the model (default ``base.en``).
"""

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner
from wavcut import cut

from vizsync.asr.faster_whisper import FasterWhisperTranscriber
from vizsync.audio.inputs import AudioMode, plan_audio
from vizsync.cli import app
from vizsync.errors import ModelLoadError
from vizsync.match.spans import ParagraphStatus
from vizsync.pipeline import AlignmentResult, ParagraphResult, run_alignment
from vizsync.script.models import Script, TextMode
from vizsync.script.parser import load_script

pytestmark = pytest.mark.slow

CLIP = Path(__file__).parents[1] / "fixtures" / "northwind.wav"
SCRIPT = Path(__file__).parents[2] / "examples" / "northwind-script.md"
MODEL = os.environ.get("VIZSYNC_TEST_MODEL", "base.en")
TOLERANCE = 0.3
"""Seconds two ways of aligning the same audio may differ."""
MARGIN = 0.05
"""Seconds of silence kept around a paragraph when it is cut into its own file."""
MIN_PAUSE = 0.3
"""Shortest pause between two paragraphs the split tests can work with."""


@pytest.fixture(scope="module")
def script() -> Script:
    return load_script(SCRIPT, TextMode.QUOTE)


@pytest.fixture(scope="module")
def clip() -> Path:
    if not CLIP.exists():
        pytest.skip(f"the fixture clip {CLIP} does not exist (see the README to record it)")
    return CLIP


@pytest.fixture(scope="module")
def transcriber(clip: Path) -> FasterWhisperTranscriber:
    return FasterWhisperTranscriber(MODEL)


def align(
    script: Script,
    files: list[Path],
    transcriber: FasterWhisperTranscriber | None,
    mode: AudioMode = AudioMode.AUTO,
) -> AlignmentResult:
    plan = plan_audio(files, [p.id for p in script.paragraphs], mode)
    try:
        return run_alignment(script, "northwind-script.md", plan, transcriber=transcriber)
    except ModelLoadError as error:
        pytest.skip(f"the speech model '{MODEL}' could not be loaded here: {error}")


@pytest.fixture(scope="module")
def whole(script: Script, clip: Path, transcriber: FasterWhisperTranscriber) -> AlignmentResult:
    return align(script, [clip], transcriber)


def describe(paragraphs: list[ParagraphResult]) -> str:
    return ", ".join(f"{p.id} {p.status.value} {p.confidence:.2f}" for p in paragraphs)


def check_pauses(result: AlignmentResult) -> None:
    for before, after in zip(result.paragraphs, result.paragraphs[1:], strict=False):
        assert before.end is not None and after.start is not None
        pause = after.start - before.end
        assert pause >= MIN_PAUSE, (
            f"the pause between {before.id} and {after.id} is only {pause:.2f} s; "
            "re-record the clip with longer pauses between paragraphs"
        )


def test_the_command_aligns_the_clip(clip: Path, tmp_path: Path) -> None:
    arguments = ["align", str(clip), "--script", str(SCRIPT), "--out", str(tmp_path)]
    result = CliRunner().invoke(app, [*arguments, "--model", MODEL])
    if result.exit_code == 1 and "Could not load the speech model" in result.output:
        pytest.skip(f"the speech model '{MODEL}' could not be loaded here")
    assert result.exit_code == 0, result.output
    data = json.loads((tmp_path / "timing.json").read_text(encoding="utf-8"))
    assert [p["status"] for p in data["paragraphs"]] == ["ok"] * 8, data["warnings"]
    assert (tmp_path / "timing.csv").exists()


def test_the_whole_clip_finds_every_paragraph(whole: AlignmentResult, script: Script) -> None:
    assert [p.id for p in whole.paragraphs] == [p.id for p in script.paragraphs]
    assert all(p.status is ParagraphStatus.OK for p in whole.paragraphs), describe(whole.paragraphs)
    starts = [p.start for p in whole.paragraphs if p.start is not None]
    assert starts == sorted(starts)
    assert starts[0] >= 0.0
    assert whole.paragraphs[-1].end is not None
    assert whole.paragraphs[-1].end <= whole.total_duration + 0.5


def test_three_parts_give_the_same_times(
    whole: AlignmentResult,
    script: Script,
    clip: Path,
    transcriber: FasterWhisperTranscriber,
    tmp_path: Path,
) -> None:
    check_pauses(whole)
    by_id = {p.id: p for p in whole.paragraphs}
    cuts = []
    for before, after in (("P3", "P4"), ("P6", "P7")):
        end, start = by_id[before].end, by_id[after].start
        assert end is not None and start is not None
        cuts.append((end + start) / 2)
    bounds = [0.0, *cuts, whole.total_duration]
    parts = []
    for number, (first, last) in enumerate(zip(bounds, bounds[1:], strict=False), start=1):
        part = tmp_path / f"part{number}.wav"
        cut(clip, part, first, last)
        parts.append(part)

    split = align(script, parts, transcriber, AudioMode.PARTS)

    assert split.mode is AudioMode.PARTS and len(split.parts) == 3
    assert [p.id for p in split.paragraphs] == [p.id for p in whole.paragraphs]
    assert all(p.status is ParagraphStatus.OK for p in split.paragraphs), describe(split.paragraphs)
    for one, other in zip(whole.paragraphs, split.paragraphs, strict=True):
        assert one.start is not None and one.end is not None
        assert other.start is not None and other.end is not None
        assert abs(one.start - other.start) <= TOLERANCE, one.id
        assert abs(one.end - other.end) <= TOLERANCE, one.id


def test_one_file_per_paragraph_gives_the_same_order_and_lengths(
    whole: AlignmentResult, script: Script, clip: Path, tmp_path: Path
) -> None:
    check_pauses(whole)
    files = []
    for paragraph in whole.paragraphs:
        assert paragraph.start is not None and paragraph.end is not None
        target = tmp_path / f"{paragraph.id}.wav"
        cut(clip, target, paragraph.start - MARGIN, paragraph.end + MARGIN)
        files.append(target)

    separate = align(script, files, None)

    assert separate.mode is AudioMode.PER_PARAGRAPH
    assert [p.id for p in separate.paragraphs] == [p.id for p in whole.paragraphs]
    assert all(p.status is ParagraphStatus.OK for p in separate.paragraphs)
    starts = [p.start for p in separate.paragraphs if p.start is not None]
    assert starts == sorted(starts) and len(starts) == len(whole.paragraphs)
    for one, other in zip(whole.paragraphs, separate.paragraphs, strict=True):
        assert one.start is not None and one.end is not None
        assert other.start is not None and other.end is not None
        assert abs((one.end - one.start) - (other.end - other.start)) <= TOLERANCE, one.id
