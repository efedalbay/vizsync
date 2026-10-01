"""Global alignment of script words against recognized words.

Needleman-Wunsch dynamic programming with affine gaps (Gotoh): a run of skipped words pays an
opening cost once, so one long gap (an unspoken paragraph, a hallucination) beats several
scattered ones. Among equally good alignments, matches are preferred from the end of both
sequences backwards; when the narrator repeats a sentence, the last take is matched.

Only a band around the diagonal from the first word pair to the last is computed. The band
starts ``|n - m| + BAND_MARGIN`` words wide on each side. The best score inside the band is
then compared with an upper bound on the score of any path that leaves it (such a path can
have only so many diagonal steps). If the bound is higher, the band is widened and the
alignment repeated. The result therefore always has the optimal score of the full table.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from rapidfuzz import fuzz

EXACT_MATCH_SCORE = 2.0
"""Score of two identical words."""
NEAR_MATCH_THRESHOLD = 0.4
"""Lowest similarity (rapidfuzz ratio, 0 to 1) that still counts as a match ("zume"/"zoomy")."""
NEAR_MATCH_SCORE_PER_SIMILARITY = 1.0
"""A near match scores its similarity times this, so always less than an exact match."""
MISMATCH_SCORE = -1.0
"""Score of pairing two dissimilar words (a substitution)."""
GAP_OPEN_SCORE = -1.0
"""Added once for every run of skipped words, on either side."""
GAP_EXTEND_SCORE = -1.0
"""Added for every skipped word, on either side."""
BAND_MARGIN = 50
"""Initial band half-width, in words, added to the length difference of the two sequences."""

# A cell's move code: bits 0-1 say which state is best at the cell; bit 2 (bit 3) says the
# script-skip (recognized-skip) state continues a run rather than opening one.
_MATCH = 0
_SKIP_SCRIPT = 1
_SKIP_RECOGNIZED = 2
_BEST_STATE = 3
_SCRIPT_RUN_CONTINUES = 4
_RECOGNIZED_RUN_CONTINUES = 8


@dataclass(frozen=True)
class WordMatch:
    """A script word matched to a recognized word.

    Attributes:
        recognized_index: Index of the recognized word it matches.
        similarity: 1.0 for identical words, lower for near matches.
    """

    recognized_index: int
    similarity: float


def word_similarity(script_word: str, recognized_word: str) -> float:
    """Return how alike two normalized words are, from 0 to 1.

    Values below ``NEAR_MATCH_THRESHOLD`` are reported as 0.
    """
    if script_word == recognized_word:
        return 1.0
    cutoff = NEAR_MATCH_THRESHOLD * 100
    return fuzz.ratio(script_word, recognized_word, score_cutoff=cutoff) / 100


def pair_score(script_word: str, recognized_word: str) -> float:
    """Return the alignment score of pairing two normalized words."""
    similarity = word_similarity(script_word, recognized_word)
    if similarity == 1.0:
        return EXACT_MATCH_SCORE
    if similarity >= NEAR_MATCH_THRESHOLD:
        return similarity * NEAR_MATCH_SCORE_PER_SIMILARITY
    return MISMATCH_SCORE


def align(script_words: Sequence[str], recognized_words: Sequence[str]) -> list[WordMatch | None]:
    """Align normalized script words with normalized recognized words.

    Returns:
        One entry per script word: the recognized word it matches, or ``None`` if it was
        skipped or paired with a dissimilar word. Matched indices are strictly increasing.
    """
    script, recognized = list(script_words), list(recognized_words)
    if not script or not recognized:
        return [None] * len(script)
    scores = _ScoreCache()
    half_width = abs(len(script) - len(recognized)) + BAND_MARGIN
    while True:
        band = _Band(len(script), len(recognized), half_width)
        moves, score = _fill(script, recognized, band, scores)
        if band.covers_everything or score >= _best_score_outside(band):
            break
        half_width = max(2 * half_width, _half_width_for(score, band))
    return _matches_on_path(script, recognized, _diagonal_steps(moves, band))


class _ScoreCache:
    """Pair scores, computed once per distinct (script word, recognized word)."""

    def __init__(self) -> None:
        self._by_script_word: dict[str, dict[str, float]] = {}

    def for_script_word(self, word: str) -> dict[str, float]:
        return self._by_script_word.setdefault(word, {})


class _Band:
    """For each table row ``i`` (script prefix length), the columns ``lo[i]..hi[i]`` computed."""

    def __init__(self, rows: int, columns: int, half_width: int) -> None:
        self.rows = rows
        self.columns = columns
        self.lo = [max(0, (i * columns) // rows - half_width) for i in range(rows + 1)]
        self.hi = [min(columns, -((-i * columns) // rows) + half_width) for i in range(rows + 1)]
        self.covers_everything = half_width >= max(rows, columns)


def _score_with_diagonal_steps(steps: int, rows: int, columns: int) -> float:
    """Best conceivable score of a path with ``steps`` diagonal steps: exact matches, one gap."""
    skipped = rows + columns - 2 * steps
    opening = GAP_OPEN_SCORE if skipped else 0.0
    return steps * EXACT_MATCH_SCORE + skipped * GAP_EXTEND_SCORE + opening


def _best_score_outside(band: _Band) -> float:
    """Upper bound on the score of any path through a cell outside the band.

    A path through cell (i, j) has at most ``min(i, j) + min(n - i, m - j)`` diagonal steps.
    That count only falls further from the band, so the cells just outside it give the bound.
    """
    rows, columns = band.rows, band.columns
    most_steps = -1
    for row in range(rows + 1):
        outside = []
        if band.lo[row] > 0:
            outside.append(band.lo[row] - 1)
        if band.hi[row] < columns:
            outside.append(band.hi[row] + 1)
        for column in outside:
            steps = min(row, column) + min(rows - row, columns - column)
            most_steps = max(most_steps, steps)
    if most_steps < 0:
        return -math.inf
    return _score_with_diagonal_steps(most_steps, rows, columns)


def _half_width_for(score: float, band: _Band) -> int:
    """Estimate the band half-width at which no outside path could beat ``score``.

    Each extra word of half-width removes one possible diagonal step from outside paths.
    """
    rows, columns = band.rows, band.columns
    perfect = _score_with_diagonal_steps(min(rows, columns), rows, columns)
    per_step = EXACT_MATCH_SCORE - 2 * GAP_EXTEND_SCORE
    return abs(rows - columns) + math.ceil((perfect - score) / per_step)


def _fill(
    script: list[str], recognized: list[str], band: _Band, scores: _ScoreCache
) -> tuple[list[bytearray], float]:
    """Compute the move code of every cell in the band, row by row, and the best total score.

    ``best`` holds, per cell, the best score of any path ending there; ``skipping_script`` the
    best score of a path whose last step skipped a script word. Only two rows of each are
    kept, as long as the whole row; cells outside the band that the next row reads are reset
    to minus infinity first. The recognized-skip state only depends on the cell to the left,
    so it is a running value.
    """
    columns = len(recognized)
    minus_infinity = -math.inf
    extend = GAP_EXTEND_SCORE
    open_ = GAP_OPEN_SCORE + GAP_EXTEND_SCORE
    previous_best = [minus_infinity] * (columns + 1)
    current_best = [minus_infinity] * (columns + 1)
    previous_skip = [minus_infinity] * (columns + 1)
    current_skip = [minus_infinity] * (columns + 1)
    moves = [_first_row(previous_best, band.hi[0])]

    for row in range(1, len(script) + 1):
        lo, hi = band.lo[row], band.hi[row]
        for column in range(band.hi[row - 1] + 1, hi + 1):
            previous_best[column] = previous_skip[column] = minus_infinity
        if lo > 0 and lo == band.lo[row - 1]:
            previous_best[lo - 1] = minus_infinity
        row_moves = bytearray(hi - lo + 1)
        left_best = left_skip = minus_infinity
        first = lo
        if lo == 0:
            opened, extended = previous_best[0] + open_, previous_skip[0] + extend
            left_best = current_skip[0] = current_best[0] = max(opened, extended)
            row_moves[0] = _SKIP_SCRIPT | (_SCRIPT_RUN_CONTINUES if extended >= opened else 0)
            first = 1
        script_word = script[row - 1]
        cached = scores.for_script_word(script_word)
        for column in range(first, hi + 1):
            heard = recognized[column - 1]
            pair = cached.get(heard)
            if pair is None:
                pair = cached[heard] = pair_score(script_word, heard)
            match = previous_best[column - 1] + pair
            opened, extended = previous_best[column] + open_, previous_skip[column] + extend
            if extended >= opened:
                skip_script, code = extended, _SCRIPT_RUN_CONTINUES
            else:
                skip_script, code = opened, 0
            opened, extended = left_best + open_, left_skip + extend
            if extended >= opened:
                left_skip = extended
                code |= _RECOGNIZED_RUN_CONTINUES
            else:
                left_skip = opened
            if match >= skip_script and match >= left_skip:
                left_best = match
            elif skip_script >= left_skip:
                left_best = skip_script
                code |= _SKIP_SCRIPT
            else:
                left_best = left_skip
                code |= _SKIP_RECOGNIZED
            current_best[column] = left_best
            current_skip[column] = skip_script
            row_moves[column - lo] = code
        moves.append(row_moves)
        previous_best, current_best = current_best, previous_best
        previous_skip, current_skip = current_skip, previous_skip
    return moves, previous_best[columns]


def _first_row(best: list[float], hi: int) -> bytearray:
    """Fill row 0 (no script word yet): only skipping recognized words, as one run."""
    best[0] = 0.0
    codes = bytearray(hi + 1)
    for column in range(1, hi + 1):
        best[column] = GAP_OPEN_SCORE + column * GAP_EXTEND_SCORE
        codes[column] = _SKIP_RECOGNIZED | (_RECOGNIZED_RUN_CONTINUES if column > 1 else 0)
    return codes


def _diagonal_steps(moves: list[bytearray], band: _Band) -> list[tuple[int, int]]:
    """Trace the best path back from the end of the table.

    Returns its diagonal steps as ``(script index, recognized index)`` pairs, in order.
    """
    row, column = band.rows, band.columns
    state = moves[row][column - band.lo[row]] & _BEST_STATE
    diagonal: list[tuple[int, int]] = []
    while row > 0 or column > 0:
        code = moves[row][column - band.lo[row]]
        if state == _MATCH:
            row, column = row - 1, column - 1
            diagonal.append((row, column))
            continues = False
        elif state == _SKIP_SCRIPT:
            row -= 1
            continues = bool(code & _SCRIPT_RUN_CONTINUES)
        else:
            column -= 1
            continues = bool(code & _RECOGNIZED_RUN_CONTINUES)
        if not continues:
            state = moves[row][column - band.lo[row]] & _BEST_STATE
    diagonal.reverse()
    return diagonal


def _matches_on_path(
    script: list[str], recognized: list[str], diagonal: list[tuple[int, int]]
) -> list[WordMatch | None]:
    matches: list[WordMatch | None] = [None] * len(script)
    for script_index, recognized_index in diagonal:
        similarity = word_similarity(script[script_index], recognized[recognized_index])
        if similarity >= NEAR_MATCH_THRESHOLD:
            matches[script_index] = WordMatch(recognized_index, similarity)
    return matches
