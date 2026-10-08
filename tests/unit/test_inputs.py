from pathlib import Path

import pytest

from vizsync.audio.inputs import (
    AudioMode,
    AudioPlan,
    expand_inputs,
    natural_sort,
    paragraph_id_in_name,
    plan_audio,
)
from vizsync.errors import AudioError


def touch(folder: Path, *names: str) -> list[Path]:
    paths = [folder / name for name in names]
    for path in paths:
        path.write_bytes(b"")
    return paths


def names(paths: list[Path]) -> list[str]:
    return [path.name for path in paths]


# --- Natural sort ---------------------------------------------------------------------


def test_natural_sort_puts_part2_before_part10() -> None:
    paths = [Path("part10.wav"), Path("part2.wav"), Path("part1.wav")]
    assert names(natural_sort(paths)) == ["part1.wav", "part2.wav", "part10.wav"]


def test_natural_sort_ignores_case_and_handles_leading_digits() -> None:
    paths = [Path("B.wav"), Path("10 intro.wav"), Path("a.wav"), Path("2 intro.wav")]
    assert names(natural_sort(paths)) == ["2 intro.wav", "10 intro.wav", "a.wav", "B.wav"]


# --- Expanding arguments -----------------------------------------------------------------


def test_explicit_files_keep_the_given_order(tmp_path: Path) -> None:
    touch(tmp_path, "b.wav", "a.wav")
    given = [tmp_path / "b.wav", tmp_path / "a.wav"]
    assert expand_inputs(given) == given


def test_folder_gives_audio_files_in_natural_order(tmp_path: Path) -> None:
    touch(tmp_path, "part10.wav", "part2.mp3", "part1.wav", "notes.txt", "cover.png")
    assert names(expand_inputs([tmp_path])) == ["part1.wav", "part2.mp3", "part10.wav"]


def test_folder_does_not_descend_into_subfolders(tmp_path: Path) -> None:
    touch(tmp_path, "a.wav")
    (tmp_path / "sub").mkdir()
    touch(tmp_path / "sub", "b.wav")
    assert names(expand_inputs([tmp_path])) == ["a.wav"]


def test_wildcard_is_expanded_and_naturally_sorted(tmp_path: Path) -> None:
    touch(tmp_path, "part10.wav", "part2.wav", "part1.wav", "other.mp3")
    result = expand_inputs([tmp_path / "part*.wav"])
    assert names(result) == ["part1.wav", "part2.wav", "part10.wav"]


def test_wildcard_in_the_folder_part(tmp_path: Path) -> None:
    (tmp_path / "day1").mkdir()
    (tmp_path / "day2").mkdir()
    touch(tmp_path / "day1", "a.wav")
    touch(tmp_path / "day2", "a.wav")
    result = expand_inputs([tmp_path / "day*" / "a.wav"])
    assert [path.parent.name for path in result] == ["day1", "day2"]


def test_arguments_can_be_mixed(tmp_path: Path) -> None:
    (tmp_path / "intro").mkdir()
    touch(tmp_path / "intro", "i2.wav", "i1.wav")
    touch(tmp_path, "z.wav", "outro.wav")
    result = expand_inputs([tmp_path / "z.wav", tmp_path / "intro", tmp_path / "out*.wav"])
    assert names(result) == ["z.wav", "i1.wav", "i2.wav", "outro.wav"]


def test_existing_file_with_wildcard_characters_is_not_a_pattern(tmp_path: Path) -> None:
    (special,) = touch(tmp_path, "take[1].wav")
    assert expand_inputs([special]) == [special]


def test_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(AudioError, match="Audio file not found") as info:
        expand_inputs([tmp_path / "part3.wav"])
    assert "part3.wav" in str(info.value)


def test_pattern_without_matches_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(AudioError, match="No audio files match"):
        expand_inputs([tmp_path / "*.wav"])


def test_folder_without_audio_is_an_error(tmp_path: Path) -> None:
    touch(tmp_path, "notes.txt")
    with pytest.raises(AudioError, match="No audio files found in folder"):
        expand_inputs([tmp_path])


def test_no_arguments_is_an_error() -> None:
    with pytest.raises(AudioError, match="No audio"):
        expand_inputs([])


# --- Paragraph identifiers in file names ----------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("P08.wav", "P8"),
        ("p8_take2.mp3", "P8"),
        ("P12.wav", "P12"),
        ("narration_P3_final.wav", "P3"),
        ("P1 intro.m4a", "P1"),
        ("P3-P4.wav", "P3"),
        ("part1.wav", None),
        ("xP3.wav", None),
        ("P.wav", None),
        ("take.wav", None),
        ("2P3.wav", None),
    ],
)
def test_paragraph_id_in_name(name: str, expected: str | None) -> None:
    assert paragraph_id_in_name(Path(name)) == expected


# --- Mode detection and planning ---------------------------------------------------------------

IDS = ["P1", "P2", "P3"]


def test_auto_picks_per_paragraph_when_every_name_has_a_known_identifier() -> None:
    files = [Path("P3.wav"), Path("p1_take2.mp3"), Path("P2.wav")]
    plan = plan_audio(files, IDS, AudioMode.AUTO)
    assert plan.mode is AudioMode.PER_PARAGRAPH
    assert [(i, f.name) for i, f in plan.paragraph_files.items()] == [
        ("P1", "p1_take2.mp3"),
        ("P2", "P2.wav"),
        ("P3", "P3.wav"),
    ]
    assert plan.ignored == []


@pytest.mark.parametrize(
    "files",
    [
        [Path("part1.wav"), Path("part2.wav")],
        [Path("P1.wav"), Path("part2.wav")],
        [Path("P1.wav"), Path("notes.wav")],
        [Path("P1.wav"), Path("notes.wav"), Path("part2.wav")],
        [Path("narration.wav")],
    ],
)
def test_auto_falls_back_to_parts(files: list[Path]) -> None:
    plan = plan_audio(files, IDS, AudioMode.AUTO)
    assert plan.mode is AudioMode.PARTS
    assert plan.paragraph_files == {}
    assert plan.ignored == []


def test_auto_ignores_a_file_that_matches_no_paragraph_when_most_files_match() -> None:
    files = [Path(f"P{n}.mp3") for n in (1, 2, 3)] + [Path("notes.mp3")]
    plan = plan_audio(files, IDS, AudioMode.AUTO)
    assert plan.mode is AudioMode.PER_PARAGRAPH
    assert list(plan.paragraph_files) == ["P1", "P2", "P3"]
    assert [path.name for path in plan.ignored] == ["notes.mp3"]


def test_auto_ignores_a_file_numbered_beyond_the_script() -> None:
    files = [Path(f"P{n:02d}.mp3") for n in (1, 2, 3, 10)]
    plan = plan_audio(files, IDS, AudioMode.AUTO)
    assert plan.mode is AudioMode.PER_PARAGRAPH
    assert [path.name for path in plan.ignored] == ["P10.mp3"]


def test_auto_takes_a_few_files_with_paragraph_numbers_as_per_paragraph_too() -> None:
    plan = plan_audio([Path("P1.wav"), Path("P9.wav")], IDS, AudioMode.AUTO)
    assert plan.mode is AudioMode.PER_PARAGRAPH
    assert list(plan.paragraph_files) == ["P1"]
    assert [path.name for path in plan.ignored] == ["P9.wav"]


def test_auto_does_not_take_half_matching_files_without_paragraph_numbers_as_per_paragraph() -> (
    None
):
    plan = plan_audio([Path("P1.wav"), Path("part2.wav")], IDS, AudioMode.AUTO)
    assert plan.mode is AudioMode.PARTS


def test_explicit_parts_ignores_identifiers_in_names() -> None:
    plan = plan_audio([Path("P1.wav"), Path("P2.wav")], IDS, AudioMode.PARTS)
    assert plan.mode is AudioMode.PARTS


def test_explicit_per_paragraph_ignores_files_without_a_matching_paragraph() -> None:
    files = [Path("P1.wav"), Path("P9.wav"), Path("notes.wav")]
    plan = plan_audio(files, IDS, AudioMode.PER_PARAGRAPH)
    assert plan.mode is AudioMode.PER_PARAGRAPH
    assert list(plan.paragraph_files) == ["P1"]
    assert [path.name for path in plan.ignored] == ["P9.wav", "notes.wav"]


def test_per_paragraph_with_no_matching_file_is_an_error() -> None:
    with pytest.raises(AudioError, match="No audio file matches"):
        plan_audio([Path("notes.wav")], IDS, AudioMode.PER_PARAGRAPH)


def test_two_files_for_one_paragraph_is_an_error() -> None:
    with pytest.raises(AudioError, match="P1 has two audio files"):
        plan_audio([Path("P1.wav"), Path("p01_take2.wav")], IDS, AudioMode.AUTO)


def test_plan_is_a_plain_value() -> None:
    plan = AudioPlan(AudioMode.PARTS, [Path("a.wav")], {}, [])
    assert plan.files == [Path("a.wav")]
