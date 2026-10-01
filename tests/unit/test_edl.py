import pytest

from vizsync.errors import OutputError
from vizsync.output.edl import EdlSettings, build_edl, to_timecode

TIMELINE = "01:00:00:00"


def settings(fps: float = 30, start: str = TIMELINE) -> EdlSettings:
    return EdlSettings.parse(fps, start)


# --- Settings ----------------------------------------------------------------------------


@pytest.mark.parametrize("fps", [23.976, 24, 25, 29.97, 30, 50, 59.94, 60])
def test_the_supported_frame_rates_are_accepted(fps: float) -> None:
    assert settings(fps).fps == fps


def test_an_unsupported_frame_rate_is_an_error_that_lists_the_choices() -> None:
    with pytest.raises(OutputError, match=r"--fps 12.*23\.976, 24, 25, 29\.97, 30, 50, 59\.94, 60"):
        settings(12)


@pytest.mark.parametrize(
    "text", ["1:00:00", "01:00:00:", "aa:00:00:00", "01:60:00:00", "01:00:60:00"]
)
def test_a_malformed_timeline_start_is_an_error(text: str) -> None:
    with pytest.raises(OutputError, match="--timeline-start"):
        settings(30, text)


def test_frames_in_the_timeline_start_must_be_below_the_frame_rate() -> None:
    with pytest.raises(OutputError, match="--timeline-start"):
        settings(30, "01:00:00:30")
    assert settings(30, "01:00:00:29").start_frame == 3600 * 30 + 29


def test_the_default_timeline_start_is_one_hour() -> None:
    assert settings(25).start_frame == 3600 * 25


# --- Timecodes ---------------------------------------------------------------------------


def test_zero_seconds_is_the_timeline_start() -> None:
    assert to_timecode(0.0, settings(30)) == "01:00:00:00"
    assert to_timecode(0.0, settings(30, "00:00:00:00")) == "00:00:00:00"


def test_seconds_become_hours_minutes_seconds_and_frames() -> None:
    assert to_timecode(61.5, settings(30)) == "01:01:01:15"
    assert to_timecode(1.5, settings(24, "00:00:00:00")) == "00:00:01:12"
    assert to_timecode(3725.0, settings(25, "00:00:00:00")) == "01:02:05:00"


def test_the_nearest_frame_is_used() -> None:
    zero = settings(30, "00:00:00:00")
    assert to_timecode(0.016, zero) == "00:00:00:00"
    assert to_timecode(0.017, zero) == "00:00:00:01"


def test_fractional_rates_count_frames_at_the_real_rate_and_label_them_at_the_nominal_one() -> None:
    zero = settings(29.97, "00:00:00:00")
    assert to_timecode(10.0, zero) == "00:00:10:00"
    assert to_timecode(60.0, zero) == "00:00:59:28"
    assert to_timecode(0.0, settings(23.976, "00:00:00:00")) == "00:00:00:00"
    assert to_timecode(60.0, settings(23.976, "00:00:00:00")) == "00:00:59:23"


# --- The file ----------------------------------------------------------------------------


def test_one_marker_per_paragraph_in_the_order_given() -> None:
    text = build_edl("northwind.md", [("P1", 0.4), ("P2", 9.8)], settings(30))
    assert text.splitlines() == [
        "TITLE: northwind",
        "FCM: NON-DROP FRAME",
        "",
        "001  001      V     C        01:00:00:12 01:00:00:13 01:00:00:12 01:00:00:13  ",
        " |C:ResolveColorBlue |M:P1 |D:1",
        "",
        "002  001      V     C        01:00:09:24 01:00:09:25 01:00:09:24 01:00:09:25  ",
        " |C:ResolveColorBlue |M:P2 |D:1",
    ]


def test_the_file_ends_with_one_newline_and_uses_no_carriage_returns() -> None:
    text = build_edl("x.md", [("P1", 1.0)], settings(30))
    assert text.endswith("|D:1\n")
    assert not text.endswith("\n\n")
    assert "\r" not in text


def test_a_marker_in_the_last_frame_of_a_second_rolls_over_correctly() -> None:
    text = build_edl("x.md", [("P1", 0.9667)], settings(30, "00:00:00:00"))
    assert "00:00:00:29 00:00:01:00 00:00:00:29 00:00:01:00" in text


def test_no_markers_gives_a_file_with_only_the_header() -> None:
    text = build_edl("x.md", [], settings(30))
    assert text == "TITLE: x\nFCM: NON-DROP FRAME\n"
