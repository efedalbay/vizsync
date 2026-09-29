import pytest

from vizsync.timefmt import format_time, parse_time


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0, "00:00.0"),
        (0.4, "00:00.4"),
        (9.8, "00:09.8"),
        (59.94, "00:59.9"),
        (59.96, "01:00.0"),
        (61.24, "01:01.2"),
        (600, "10:00.0"),
        (3599.94, "59:59.9"),
        (3599.96, "1:00:00.0"),
        (3600, "1:00:00.0"),
        (3725.5, "1:02:05.5"),
        (36000, "10:00:00.0"),
    ],
)
def test_format_time(seconds: float, text: str) -> None:
    assert format_time(seconds) == text


def test_format_time_rejects_negative() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        format_time(-0.1)


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("00:00.0", 0.0),
        ("00:09.8", 9.8),
        ("01:01.5", 61.5),
        ("10:00", 600.0),
        ("1:02:05.5", 3725.5),
        ("00:21", 21.0),
    ],
)
def test_parse_time(text: str, seconds: float) -> None:
    assert parse_time(text) == pytest.approx(seconds)


@pytest.mark.parametrize("seconds", [0.0, 0.4, 59.9, 61.5, 3599.9, 3725.5])
def test_round_trip(seconds: float) -> None:
    assert parse_time(format_time(seconds)) == pytest.approx(seconds)


@pytest.mark.parametrize("text", ["", "abc", "1:2:3:4", "12", "01:60.0", "1:60:00", "-01:00"])
def test_parse_time_rejects_bad_text(text: str) -> None:
    with pytest.raises(ValueError, match="time"):
        parse_time(text)
