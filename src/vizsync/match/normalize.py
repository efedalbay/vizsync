"""Turn script text and recognized words into comparable lowercase words.

Both sides go through :func:`normalize_text`, so the rules only have to be consistent:

- Unicode NFKC, then casefold.
- Apostrophes (``'`` and the typographic U+2019) are kept only between two letters or digits
  ("don't", "Northwind's"); elsewhere they are dropped ("drivers'", "'90s").
- Dashes of every kind and ``/`` separate words ("twenty-five" gives "twenty", "five").
- A ``.`` between two digits is a decimal point and is kept ("3.5"); every other punctuation
  mark or symbol is removed without separating, so "25,000" becomes "25000" and "U.S." "us".
- Digits are kept as written; numbers are never spelled out.
"""

import unicodedata
from collections.abc import Callable, Sequence

from vizsync.asr.base import Word

_APOSTROPHES = {"'", "\u2019", "\u02bc"}  # plain, typographic, modifier letter
_SEPARATORS = {"/"}
_DECIMAL_POINT = "."


def normalize_text(text: str) -> list[str]:
    """Return the comparable words of ``text``, in order. Punctuation-only text gives ``[]``."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    kept = [_normalize_char(folded, index) for index in range(len(folded))]
    return "".join(kept).split()


def normalize_words(words: Sequence[Word]) -> list[Word]:
    """Normalize recognized words, keeping their times.

    A word that normalizes to nothing (punctuation only) is dropped. A word that normalizes to
    several words ("twenty-five") is split, and its time interval is shared evenly between them.
    """
    result: list[Word] = []
    for word in words:
        result.extend(_split_word(word, normalize_text(word.text)))
    return result


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
