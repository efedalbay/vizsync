import json
import math
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
    relaxed = env.align(wav, "--formats", "json")
    assert relaxed.exit_code == 0
    assert env.timing()["paragraphs"][3]["status"] == "low_confidence"
    assert len(env.timing()["warnings"]) == 1
    assert env.align(wav, "--formats", "json", "--strict").exit_code == 1


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


def test_chapters_and_markers_are_written_by_default(env: Env) -> None:
    (wav,) = env.audio("all.wav")
    assert env.align(wav).exit_code == 0
    paragraphs = env.timing()["paragraphs"]
    chapters = (env.out / "chapters.txt").read_text(encoding="utf-8").splitlines()
    assert chapters[0] == "00:00 One"
    assert chapters[1] == f"00:{int(paragraphs[2]['start']):02d} Two"
    edl = (env.out / "markers.edl").read_text(encoding="utf-8")
    assert edl.startswith("TITLE: demo\nFCM: NON-DROP FRAME\n")
    assert [line.split("|M:")[1].split(" ")[0] for line in edl.splitlines() if "|M:" in line] == [
        "P1",
        "P2",
        "P3",
        "P4",
    ]


def test_only_chapters_or_only_markers_can_be_asked_for(env: Env) -> None:
    (wav,) = env.audio("all.wav")
    assert env.align(wav, "--formats", "edl").exit_code == 0
    assert (env.out / "markers.edl").exists()
    assert not (env.out / "chapters.txt").exists()
    assert not (env.out / "timing.json").exists()
    assert env.align(wav, "--formats", "chapters").exit_code == 0
    assert (env.out / "chapters.txt").exists()


def test_chapter_warnings_are_printed_stored_in_timing_json_and_count_for_strict(
    env: Env, plain: Callable[[str], str]
) -> None:
    (wav,) = env.audio("all.wav")
    result = env.align(wav)
    assert result.exit_code == 0
    assert "warning: chapters: only 2 chapters, YouTube needs at least 3." in plain(result.stderr)
    assert "chapters: only 2 chapters, YouTube needs at least 3." in env.timing()["warnings"]
    assert env.align(wav, "--strict").exit_code == 1


def test_no_chapter_warnings_without_the_chapters_format(env: Env) -> None:
    (wav,) = env.audio("all.wav")
    assert env.align(wav, "--formats", "json,edl", "--strict").exit_code == 0
    assert env.timing()["warnings"] == []


def test_fps_and_timeline_start_set_the_marker_timecodes(env: Env) -> None:
    (wav,) = env.audio("all.wav")
    result = env.align(
        wav, "--formats", "json,edl", "--fps", "25", "--timeline-start", "00:00:00:00"
    )
    assert result.exit_code == 0
    edl = (env.out / "markers.edl").read_text(encoding="utf-8")
    assert "001  001      V     C        00:00:00:00 00:00:00:01 00:00:00:00 00:00:00:01  " in edl
    frame = math.floor(env.timing()["paragraphs"][1]["start"] * 25 + 0.5)
    assert f"00:00:{frame // 25:02d}:{frame % 25:02d} " in edl


def test_markers_use_one_hour_and_30_fps_unless_told_otherwise(env: Env) -> None:
    (wav,) = env.audio("all.wav")
    assert env.align(wav, "--formats", "edl").exit_code == 0
    edl = (env.out / "markers.edl").read_text(encoding="utf-8")
    assert "001  001      V     C        01:00:00:00 01:00:00:01 01:00:00:00 01:00:00:01  " in edl


def test_an_unsupported_fps_stops_before_any_listening(
    env: Env, plain: Callable[[str], str]
) -> None:
    (wav,) = env.audio("all.wav")
    result = env.align(wav, "--fps", "12")
    assert result.exit_code == 1
    assert "Unsupported --fps 12" in plain(result.stderr)
    assert env.stub.calls == []
    assert env.created == []


def test_a_bad_timeline_start_stops_before_any_listening(
    env: Env, plain: Callable[[str], str]
) -> None:
    (wav,) = env.audio("all.wav")
    result = env.align(wav, "--timeline-start", "1:00:00")
    assert result.exit_code == 1
    assert "Invalid --timeline-start" in plain(result.stderr)
    assert env.stub.calls == []


def test_fps_is_not_checked_when_no_markers_are_written(env: Env) -> None:
    (wav,) = env.audio("all.wav")
    assert env.align(wav, "--formats", "json", "--fps", "12").exit_code == 0


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


# --- Joining paragraph files into one narration ------------------------------------------------


def wav_frames(path: Path) -> tuple[int, int]:
    import wave

    with wave.open(str(path), "rb") as wav:
        return wav.getnframes(), wav.getframerate()


def paragraph_wavs(env: Env, seconds: float = 1.0, rate: int = 16000) -> list[Path]:
    from fakes import write_silent_wav

    return [write_silent_wav(env.folder / f"P{n}.wav", seconds, rate) for n in (1, 2, 3, 4)]


def test_join_writes_the_narration_and_times_that_match_it(env: Env) -> None:
    files = paragraph_wavs(env)
    result = env.align(*files, "--join")
    assert result.exit_code == 0
    frames, rate = wav_frames(env.out / "narration.wav")
    data = env.timing()
    assert data["mode"] == "per-paragraph"
    assert data["total_duration"] == frames / rate == 6.4
    assert data["audio"] == [{"file": "narration.wav", "offset": 0.0, "duration": 6.4}]
    # P1 | 0.6 | P2 | 1.2 (new chapter) | P3 | 0.6 | P4
    assert [p["start"] for p in data["paragraphs"]] == [0.0, 1.6, 3.8, 5.4]
    assert [p["end"] for p in data["paragraphs"]] == [1.0, 2.6, 4.8, 6.4]
    assert env.stub.calls == []
    assert env.created == []


def test_the_other_files_use_the_joined_times(env: Env) -> None:
    files = paragraph_wavs(env)
    assert env.align(*files, "--join").exit_code == 0
    assert (env.out / "chapters.txt").read_text(encoding="utf-8").splitlines()[:2] == [
        "00:00 One",
        "00:03 Two",
    ]


def test_the_gaps_can_be_changed(env: Env) -> None:
    files = paragraph_wavs(env)
    result = env.align(*files, "--join", "--paragraph-gap", "0.1", "--chapter-gap", "0.5")
    assert result.exit_code == 0
    assert [p["start"] for p in env.timing()["paragraphs"]] == [0.0, 1.1, 2.6, 3.7]
    assert wav_frames(env.out / "narration.wav")[0] == round(4.7 * 16000)


def test_a_missing_paragraph_file_is_missing_in_the_joined_result(env: Env) -> None:
    files = [f for f in paragraph_wavs(env) if f.stem != "P3"]
    result = env.align(*files, "--join")
    assert result.exit_code == 2
    assert env.timing()["paragraphs"][2]["status"] == "missing"
    assert wav_frames(env.out / "narration.wav")[0] == round(4.8 * 16000)


def test_the_files_are_reported_on_the_console(env: Env, plain: Callable[[str], str]) -> None:
    files = paragraph_wavs(env)
    result = env.align(*files, "--join")
    assert "Joined 4 files into" in plain(result.stderr)
    assert "narration.wav" in plain(result.stdout)


def test_without_join_nothing_is_joined(env: Env) -> None:
    files = paragraph_wavs(env)
    env.durations.update({f.name: 1.0 for f in files})
    assert env.align(*files).exit_code == 0
    assert not (env.out / "narration.wav").exists()
    assert env.timing()["audio"][0]["file"] == "P1.wav"


@pytest.mark.parametrize("option", [["--paragraph-gap", "1"], ["--chapter-gap", "1"], ["--trim"]])
def test_the_gap_and_trim_options_need_join(
    env: Env, plain: Callable[[str], str], option: list[str]
) -> None:
    files = paragraph_wavs(env)
    result = env.align(*files, *option)
    assert result.exit_code == 1
    assert f"{option[0]} only works with --join" in plain(result.output)
    assert not env.out.exists()


def test_a_negative_gap_is_a_usage_error(env: Env) -> None:
    assert env.align(*paragraph_wavs(env), "--join", "--paragraph-gap", "-1").exit_code == 1


def test_join_needs_one_file_per_paragraph(env: Env, plain: Callable[[str], str]) -> None:
    (wav,) = env.audio("all.wav")
    result = env.align(wav, "--join")
    assert result.exit_code == 1
    assert "--join needs one file per paragraph" in plain(result.stderr)
    assert env.stub.calls == [] and not env.out.exists()


def test_files_of_different_sample_rates_stop_the_run(
    env: Env, plain: Callable[[str], str]
) -> None:
    from fakes import write_silent_wav

    files = paragraph_wavs(env)
    files[2] = write_silent_wav(env.folder / "P3.wav", 1.0, 22050)
    result = env.align(*files, "--join")
    assert result.exit_code == 1
    assert "P3.wav is 22050 Hz, mono, 16-bit" in plain(result.stderr)
    assert "one format" in plain(result.stderr)
    assert not env.out.exists()


def test_a_file_that_is_not_a_wav_stops_the_run(env: Env, plain: Callable[[str], str]) -> None:
    files = paragraph_wavs(env)
    mp3 = env.folder / "P5.mp3"
    mp3.write_bytes(b"ID3" + b"\x00" * 50)
    script = env.script.read_text(encoding="utf-8") + "\nP5 — x\n\n> Fifth.\n"
    env.script.write_text(script, encoding="utf-8")
    result = env.align(*files, mp3, "--join")
    assert result.exit_code == 1
    assert "plain PCM WAV" in plain(result.stderr)


def test_trim_cuts_the_silence_around_the_speech(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    files = paragraph_wavs(env, seconds=2.0)
    monkeypatch.setattr("vizsync.cli.vad_speech_bounds", lambda path: (0.5, 1.5))
    result = env.align(*files, "--join", "--trim")
    assert result.exit_code == 0
    # Every file keeps 0.05 s around the speech: 1.1 s each.
    lengths = [p["end"] - p["start"] for p in env.timing()["paragraphs"]]
    assert lengths == pytest.approx([1.1] * 4)
    assert wav_frames(env.out / "narration.wav")[0] == round(env.timing()["total_duration"] * 16000)


def test_trim_warns_about_a_file_without_speech(
    env: Env, monkeypatch: pytest.MonkeyPatch, plain: Callable[[str], str]
) -> None:
    files = paragraph_wavs(env)
    monkeypatch.setattr("vizsync.cli.vad_speech_bounds", lambda path: None)
    result = env.align(*files, "--join", "--trim")
    assert result.exit_code == 0
    assert "P1.wav: no speech found, not trimmed." in plain(result.stderr)
