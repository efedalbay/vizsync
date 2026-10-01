import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeTranscriber, timed_words
from typer.testing import CliRunner

from vizsync.asr.base import Word
from vizsync.cli import app
from vizsync.errors import TranscriptionError

runner = CliRunner()

SCRIPT_TEXT = """\
## 1. Bir / 1. One

P1 — x

> Northwind opened its first office in 2016.

P2 — x

> The team grew quickly after that.

## 2. İki / 2. Two

P3 — x

> Revenue doubled within one year.

P4 — x

> Then the biggest customer left.
"""
SPOKEN = [
    "Northwind opened its first office in 2016",
    "The team grew quickly after that",
    "Revenue doubled within one year",
    "Then the biggest customer left",
]


def narration(indexes: list[int], start: float = 0.0) -> list[Word]:
    words: list[Word] = []
    clock = start
    for index in indexes:
        chunk = timed_words(SPOKEN[index], start=clock)
        words += chunk
        clock = chunk[-1].end + 1.0
    return words


def garbled_last_paragraph() -> list[Word]:
    """The whole narration, with two of the five words of P4 misheard (confidence 0.6)."""
    words = narration([0, 1, 2, 3])
    for index in (-2, -3):
        words[index] = Word(text="banana", start=words[index].start, end=words[index].end)
    return words


class Stub(FakeTranscriber):
    """A transcriber for the CLI: remembers how it was created and says if it is cached."""

    def __init__(self, words: Any, *, cached: bool = True) -> None:
        super().__init__(words)
        self.cached = cached
        self.model_name = "small.en"

    def is_cached(self) -> bool:
        return self.cached


class Env:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.folder = tmp_path
        self.script = tmp_path / "demo.md"
        self.script.write_text(SCRIPT_TEXT, encoding="utf-8")
        self.out = tmp_path / "result"
        self.durations: dict[str, float] = {}
        self.created: list[tuple[str, str]] = []
        self.stub = Stub(narration([0, 1, 2, 3]))
        monkeypatch.setattr(
            "vizsync.cli.read_duration", lambda path: self.durations.get(path.name, 40.0)
        )
        monkeypatch.setattr("vizsync.cli.FasterWhisperTranscriber", self._factory)

    def _factory(self, model: str, *, device: str) -> Stub:
        self.created.append((model, device))
        return self.stub

    def audio(self, *names: str) -> list[Path]:
        paths = [self.folder / name for name in names]
        for path in paths:
            path.write_bytes(b"")
        return paths

    def align(self, *arguments: str | Path) -> Any:
        base = ["align", "--script", str(self.script), "--out", str(self.out)]
        return runner.invoke(app, [*base, *map(str, arguments)])

    def timing(self) -> dict[str, Any]:
        return json.loads((self.out / "timing.json").read_text(encoding="utf-8"))


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    return Env(tmp_path, monkeypatch)


# --- Parts mode ------------------------------------------------------------------------


def test_one_recording(env: Env, plain: Callable[[str], str]) -> None:
    (wav,) = env.audio("all.wav")
    result = env.align(wav)
    assert result.exit_code == 0
    out = plain(result.stdout)
    rows = [line for line in out.splitlines() if line.startswith("P")]
    assert len(rows) == 4
    assert rows[0].startswith("P1") and " -> " in rows[0] and rows[0].rstrip().endswith("ok")
    assert "→" not in out
    assert "4 ok, 0 low confidence, 0 missing" in out
    data = env.timing()
    assert data["mode"] == "parts"
    assert data["total_duration"] == 40.0
    assert [p["status"] for p in data["paragraphs"]] == ["ok"] * 4
    assert (env.out / "timing.csv").exists()


def test_time_summary_in_parts_mode(env: Env, plain: Callable[[str], str]) -> None:
    (wav,) = env.audio("all.wav")
    result = env.align(wav)
    assert "speech recognition" in plain(result.stderr)


def test_options_reach_the_transcriber(env: Env) -> None:
    (wav,) = env.audio("all.wav")
    result = env.align(wav, "--model", "base.en", "--device", "cpu", "--language", "tr")
    assert result.exit_code == 0
    assert env.created == [("base.en", "cpu")]
    assert env.stub.calls == [(wav, "tr")]


def test_offset_and_gap(env: Env) -> None:
    first, second = env.audio("part1.wav", "part2.wav")
    env.durations = {"part1.wav": 20.0, "part2.wav": 20.0}
    env.stub = Stub({first: narration([0, 1]), second: narration([2, 3])})
    result = env.align(first, second, "--offset", "5", "--gap", "1")
    assert result.exit_code == 0
    data = env.timing()
    assert [a["offset"] for a in data["audio"]] == [5.0, 26.0]
    assert data["offset"] == 5.0
    assert data["paragraphs"][0]["start"] == pytest.approx(5.0)
    assert data["total_duration"] == 41.0


def test_wildcard_is_expanded_in_natural_order(env: Env) -> None:
    for name in ("part10.wav", "part2.wav", "part1.wav"):
        env.audio(name)
    env.stub = Stub(
        {
            env.folder / f"part{n}.wav": narration([0, 1, 2, 3][: 1 + (n == 1) * 3])
            for n in (1, 2, 10)
        }
    )
    result = env.align(env.folder / "part*.wav")
    assert result.exit_code in (0, 2)
    assert [call[0].name for call in env.stub.calls] == ["part1.wav", "part2.wav", "part10.wav"]


def test_folder_argument(env: Env) -> None:
    folder = env.folder / "takes"
    folder.mkdir()
    (folder / "a.wav").write_bytes(b"")
    result = env.align(folder)
    assert result.exit_code == 0
    assert [call[0].name for call in env.stub.calls] == ["a.wav"]


def test_missing_paragraph_exits_with_2_and_still_writes_files(
    env: Env, plain: Callable[[str], str]
) -> None:
    env.stub = Stub(narration([0, 2, 3]))
    (wav,) = env.audio("all.wav")
    result = env.align(wav)
    assert result.exit_code == 2
    assert "P2: not found in the audio." in plain(result.stderr)
    data = env.timing()
    assert data["paragraphs"][1]["status"] == "missing"
    assert data["paragraphs"][1]["start"] is None
    assert any(
        line.startswith("P2") and "not found" in line for line in plain(result.stdout).splitlines()
    )


def test_low_confidence_is_a_warning_and_strict_makes_it_exit_1(env: Env) -> None:
    words = garbled_last_paragraph()
    env.stub = Stub(words)
    (wav,) = env.audio("all.wav")
    relaxed = env.align(wav)
    assert relaxed.exit_code == 0
    assert env.timing()["paragraphs"][3]["status"] == "low_confidence"
    assert len(env.timing()["warnings"]) == 1
    assert env.align(wav, "--strict").exit_code == 1


def test_min_confidence_option(env: Env) -> None:
    words = garbled_last_paragraph()
    env.stub = Stub(words)
    (wav,) = env.audio("all.wav")
    env.align(wav, "--min-confidence", "0.5")
    assert env.timing()["paragraphs"][3]["status"] == "ok"


def test_model_download_notice(env: Env, plain: Callable[[str], str]) -> None:
    env.stub = Stub(narration([0, 1, 2, 3]), cached=False)
    (wav,) = env.audio("all.wav")
    result = env.align(wav)
    assert "Downloading the speech model 'small.en' (about 484 MB)" in plain(result.stderr)


def test_no_download_notice_when_the_model_is_saved(env: Env, plain: Callable[[str], str]) -> None:
    (wav,) = env.audio("all.wav")
    assert "Downloading" not in plain(env.align(wav).stderr)


# --- Per-paragraph mode ----------------------------------------------------------------


def test_per_paragraph_files_are_detected_and_need_no_model(env: Env) -> None:
    files = env.audio("P1.wav", "P2.wav", "P3.wav", "P4.wav")
    env.durations = {"P1.wav": 4.0, "P2.wav": 3.0, "P3.wav": 5.0, "P4.wav": 2.0}
    result = env.align(*files)
    assert result.exit_code == 0
    assert env.created == []
    data = env.timing()
    assert data["mode"] == "per-paragraph"
    assert [(p["start"], p["end"]) for p in data["paragraphs"]] == [
        (0.0, 4.0), (4.0, 7.0), (7.0, 12.0), (12.0, 14.0)
    ]  # fmt: skip
    assert data["total_duration"] == 14.0


def test_forcing_parts_mode_on_files_named_like_paragraphs(env: Env) -> None:
    files = env.audio("P1.wav", "P2.wav")
    result = env.align(*files, "--mode", "parts")
    assert result.exit_code in (0, 2)
    assert env.timing()["mode"] == "parts"


def test_paragraph_without_a_file_exits_with_2(env: Env, plain: Callable[[str], str]) -> None:
    files = env.audio("P1.wav", "P2.wav", "notes_P9.wav")
    result = env.align(*files, "--mode", "per-paragraph")
    assert result.exit_code == 2
    err = plain(result.stderr)
    assert "P3: no audio file." in err
    assert "notes_P9.wav: matches no paragraph of the script, ignored." in err


# --- Output files and formats ----------------------------------------------------------


def test_output_folder_is_created(env: Env) -> None:
    (wav,) = env.audio("all.wav")
    env.out = env.folder / "deep" / "er"
    assert env.align(wav).exit_code == 0
    assert (env.out / "timing.json").exists()


def test_default_output_folder_is_out(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    (wav,) = env.audio("all.wav")
    monkeypatch.chdir(env.folder)
    result = runner.invoke(app, ["align", str(wav), "--script", str(env.script)])
    assert result.exit_code == 0
    assert (env.folder / "out" / "timing.json").exists()


def test_only_the_requested_formats_are_written(env: Env) -> None:
    (wav,) = env.audio("all.wav")
    assert env.align(wav, "--formats", "json").exit_code == 0
    assert (env.out / "timing.json").exists()
    assert not (env.out / "timing.csv").exists()
    csv_only = env.align(wav, "--formats", " CSV ")
    assert csv_only.exit_code == 0


def test_formats_that_come_later_are_skipped_with_a_notice(
    env: Env, plain: Callable[[str], str]
) -> None:
    (wav,) = env.audio("all.wav")
    result = env.align(wav)
    assert "chapters.txt and markers.edl are not available yet" in plain(result.stderr)
    assert not (env.out / "chapters.txt").exists()
    assert not (env.out / "markers.edl").exists()


def test_unknown_format_is_a_usage_error(env: Env, plain: Callable[[str], str]) -> None:
    (wav,) = env.audio("all.wav")
    result = env.align(wav, "--formats", "json,pdf")
    assert result.exit_code == 1
    assert "pdf" in plain(result.output)
    assert env.stub.calls == []


def test_unwritable_output_folder(env: Env, plain: Callable[[str], str]) -> None:
    (wav,) = env.audio("all.wav")
    env.out.write_text("I am a file", encoding="utf-8")
    result = env.align(wav)
    assert result.exit_code == 1
    assert "Cannot" in plain(result.stderr)


# --- Errors ----------------------------------------------------------------------------


def test_missing_audio_file(env: Env, plain: Callable[[str], str]) -> None:
    result = env.align(env.folder / "nope.wav")
    assert result.exit_code == 1
    assert plain(result.stderr).strip() == f"Audio file not found: {env.folder / 'nope.wav'}"


def test_broken_script_lists_every_problem(env: Env, plain: Callable[[str], str]) -> None:
    env.script.write_text("P1 — x\n\nP2 — y\n", encoding="utf-8")
    (wav,) = env.audio("all.wav")
    result = env.align(wav)
    assert result.exit_code == 1
    err = plain(result.stderr)
    assert "P1 has no blockquote" in err and "P2 has no blockquote" in err
    assert "2 problems found" in err
    assert env.stub.calls == []


def test_missing_script(env: Env, plain: Callable[[str], str]) -> None:
    env.script.unlink()
    (wav,) = env.audio("all.wav")
    result = env.align(wav)
    assert result.exit_code == 1
    assert "Script file not found" in plain(result.stderr)


def test_transcription_error_is_shown_without_a_traceback(
    env: Env, plain: Callable[[str], str]
) -> None:
    def fail(*args: Any, **kwargs: Any) -> list[Word]:
        raise TranscriptionError("Could not load the speech model 'small.en' (offline)")

    env.stub.transcribe = fail  # type: ignore[method-assign]
    (wav,) = env.audio("all.wav")
    result = env.align(wav)
    assert result.exit_code == 1
    assert "Could not load the speech model" in plain(result.stderr)
    assert "Traceback" not in plain(result.output)


@pytest.mark.parametrize(
    "option", [["--offset", "-1"], ["--gap", "-0.5"], ["--min-confidence", "1.5"]]
)
def test_out_of_range_options_exit_with_1(env: Env, option: list[str]) -> None:
    (wav,) = env.audio("all.wav")
    assert env.align(wav, *option).exit_code == 1


def test_invalid_choice_exits_with_1_not_2(env: Env) -> None:
    (wav,) = env.audio("all.wav")
    assert env.align(wav, "--mode", "sideways").exit_code == 1
    assert env.align(wav, "--device", "tpu").exit_code == 1


def test_script_option_is_required(env: Env) -> None:
    (wav,) = env.audio("all.wav")
    assert runner.invoke(app, ["align", str(wav)]).exit_code == 1


def test_audio_argument_is_required(env: Env) -> None:
    assert runner.invoke(app, ["align", "--script", str(env.script)]).exit_code == 1


def test_lengths_round_like_the_times(env: Env, plain: Callable[[str], str]) -> None:
    files = env.audio("P1.wav", "P2.wav")
    env.durations = {"P1.wav": 4.0, "P2.wav": 3.25}
    out = plain(env.align(*files, "--mode", "per-paragraph").stdout)
    p2 = next(line for line in out.splitlines() if line.startswith("P2"))
    assert "00:04.0 ->" in p2 and "00:07.3" in p2 and "3.3 s" in p2
