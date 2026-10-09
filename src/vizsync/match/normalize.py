"""Turn script text and recognized words into comparable lowercase words.

Both sides go through the same rules, so the rules only have to be consistent:

- Unicode NFKC, then casefold.
- Apostrophes (``'`` and the typographic U+2019) are kept only between two letters or digits
  ("don't", "Northwind's"); elsewhere they are dropped ("drivers'", "'90s").
- Dashes of every kind and ``/`` separate words ("north-east" gives "north", "east").
- A ``.`` between two digits is a decimal point and is kept ("3.5"); every other punctuation
  mark or symbol is removed without separating, so "25,000" becomes "25000" and "U.S." "us".
- Digits are kept as written. A run of spelled-out English number words becomes digits, the
  way speech recognition writes numbers: "three hundred and seventy-five" gives "375",
  "twenty-five thousand" "25000", "two point five" "2.5". "million", "billion" and
  "trillion" stay separate words ("375", "million"). Only whole cardinals up to 999,999 with an
  optional decimal fraction are read; a word that cannot extend the number starts a new one
  ("twenty twenty-six" gives "20", "26"). Ordinals, fractions, years and "a hundred" are left
  as words. An "and" is part of a number only after "hundred", or after "thousand" when
  fewer than a hundred follows ("two thousand and five" gives "2005").
"""

import unicodedata
from collections.abc import Callable, Sequence

from vizsync.asr.base import Word

_APOSTROPHES = {"'", "\u2019", "\u02bc"}  # plain, typographic, modifier letter
_SEPARATORS = {"/"}
_DECIMAL_POINT = "."

_UNITS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
}
_TEENS = {
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_FRACTION_DIGITS = {"zero": "0", "oh": "0"} | {word: str(value) for word, value in _UNITS.items()}

_Number = tuple[int, int]
"""A value read from the tokens, and the index of the first token after it."""


def normalize_text(text: str) -> list[str]:
    """Return the comparable words of ``text``, in order. Punctuation-only text gives ``[]``."""
    return [token for token, _, _ in _merge_numbers(_split_text(text))]


def normalize_words(words: Sequence[Word]) -> list[Word]:
    """Normalize recognized words, keeping their times.

    A word that normalizes to nothing (punctuation only) is dropped. A word that normalizes to
    several words ("north-east") is split, and its time interval is shared evenly between them.
    A spelled-out number spoken as several words becomes one word, from the start of its first
    part to the end of its last.
    """
    pieces = [piece for word in words for piece in _split_word(word, _split_text(word.text))]
    return [
        Word(text=token, start=pieces[first].start, end=pieces[last].end)
        for token, first, last in _merge_numbers([piece.text for piece in pieces])
    ]


def _split_text(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKC", text).casefold()
    kept = [_normalize_char(folded, index) for index in range(len(folded))]
    return "".join(kept).split()


def _normalize_char(text: str, index: int) -> str:
    char = text[index]
    if char.isspace():
        return " "
    if char in _APOSTROPHES:
        return "'" if _between(text, index, str.isalnum) else ""
    if char == _DECIMAL_POINT and _between(text, index, str.isdigit):
        return char
    category = unicodedata.category(char)
    if category == "Pd" or char in _SEPARATORS:
        return " "
    if category[0] in "PS":
        return ""
    return char


def _between(text: str, index: int, test: Callable[[str], bool]) -> bool:
    return 0 < index < len(text) - 1 and test(text[index - 1]) and test(text[index + 1])


def _split_word(word: Word, tokens: list[str]) -> list[Word]:
    if len(tokens) == 1:
        return [Word(text=tokens[0], start=word.start, end=word.end)]
    step = (word.end - word.start) / len(tokens) if tokens else 0.0
    return [
        Word(
            text=token,
            start=word.start + index * step,
            end=word.end if index == len(tokens) - 1 else word.start + (index + 1) * step,
        )
        for index, token in enumerate(tokens)
    ]


def _merge_numbers(tokens: Sequence[str]) -> list[tuple[str, int, int]]:
    """Replace every run of number words by its digits.

    Returns each resulting token with the indices of the first and last input token it covers.
    """
    result: list[tuple[str, int, int]] = []
    index = 0
    while index < len(tokens):
        number = _read_number(tokens, index)
        if number is None:
            result.append((tokens[index], index, index))
            index += 1
        else:
            digits, stop = number
            result.append((digits, index, stop - 1))
            index = stop
    return result


def _read_number(tokens: Sequence[str], index: int) -> tuple[str, int] | None:
    if _at(tokens, index) == "zero":
        whole: _Number | None = (0, index + 1)
    else:
        whole = _read_thousands(tokens, index)
    if whole is None:
        return None
    value, stop = whole
    fraction, stop = _read_fraction(tokens, stop)
    return f"{value}{fraction}", stop


def _read_fraction(tokens: Sequence[str], index: int) -> tuple[str, int]:
    if _at(tokens, index) != "point":
        return "", index
    stop = index + 1
    while _at(tokens, stop) in _FRACTION_DIGITS:
        stop += 1
    if stop == index + 1:
        return "", index
    return "." + "".join(_FRACTION_DIGITS[token] for token in tokens[index + 1 : stop]), stop


def _read_thousands(tokens: Sequence[str], index: int) -> _Number | None:
    head = _read_hundreds(tokens, index)
    if head is None or _at(tokens, head[1]) != "thousand":
        return head
    value, stop = head[0] * 1000, head[1] + 1
    if _at(tokens, stop) == "and":
        tail = _read_tens(tokens, stop + 1)
    else:
        tail = _read_hundreds(tokens, stop)
    if tail is None or _at(tokens, tail[1]) in ("hundred", "thousand"):
        return value, stop
    return value + tail[0], tail[1]


def _read_hundreds(tokens: Sequence[str], index: int) -> _Number | None:
    if _at(tokens, index) not in _UNITS or _at(tokens, index + 1) != "hundred":
        return _read_tens(tokens, index)
    value, stop = _UNITS[tokens[index]] * 100, index + 2
    tail = _read_tens(tokens, stop + 1 if _at(tokens, stop) == "and" else stop)
    if tail is None or _at(tokens, tail[1]) == "hundred":
        return value, stop
    return value + tail[0], tail[1]


def _read_tens(tokens: Sequence[str], index: int) -> _Number | None:
    token = _at(tokens, index)
    if token in _TENS:
        unit = _at(tokens, index + 1)
        if unit in _UNITS:
            return _TENS[token] + _UNITS[unit], index + 2
        return _TENS[token], index + 1
    if token in _TEENS:
        return _TEENS[token], index + 1
    if token in _UNITS:
        return _UNITS[token], index + 1
    return None


def _at(tokens: Sequence[str], index: int) -> str:
    return tokens[index] if index < len(tokens) else ""
