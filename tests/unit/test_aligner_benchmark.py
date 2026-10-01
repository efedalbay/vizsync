"""The aligner must handle a 30-minute narration (about 4,500 words) in under 10 seconds."""

import random
import time

from vizsync.match.aligner import align

WORD_COUNT = 4_500
ERROR_RATE = 0.05
TIME_LIMIT_SECONDS = 10.0
SEED = 20_260_101
FUNCTION_WORDS = "the a of and to in is that it for on was with as at by northwind"
SYLLABLES = ["nor", "th", "wind", "ka", "lo", "mi", "ter", "san", "vel", "dor", "ap", "ri", "um"]


def _vocabulary(rng: random.Random) -> list[str]:
    function_words = FUNCTION_WORDS.split()
    content = {"".join(rng.choices(SYLLABLES, k=rng.randint(2, 4))) for _ in range(3_000)}
    return function_words + sorted(content - set(function_words))


def _make_case(rng: random.Random) -> tuple[list[str], list[str], dict[int, int]]:
    """Return script words, recognized words, and script index -> correct recognized index."""
    vocabulary = _vocabulary(rng)
    weights = [1.0 / (rank + 1) for rank in range(len(vocabulary))]
    script = rng.choices(vocabulary, weights=weights, k=WORD_COUNT)
    heard: list[str] = []
    expected: dict[int, int] = {}
    for index, word in enumerate(script):
        roll = rng.random()
        if roll < ERROR_RATE / 3:
            continue
        if roll < 2 * ERROR_RATE / 3:
            heard.append(rng.choice(vocabulary))
            continue
        if roll < ERROR_RATE:
            heard.append(rng.choice(vocabulary))
        expected[index] = len(heard)
        heard.append(word)
    return script, heard, expected


def test_aligns_4500_words_with_5_percent_errors_quickly() -> None:
    script, heard, expected = _make_case(random.Random(SEED))

    began = time.perf_counter()
    matches = align(script, heard)
    elapsed = time.perf_counter() - began

    assert len(matches) == len(script)
    correct = 0
    for script_index, heard_index in expected.items():
        match = matches[script_index]
        if match is not None and match.recognized_index == heard_index:
            correct += 1
    print(f"align: {elapsed:.2f} s, {correct}/{len(expected)} surviving words matched correctly")
    assert correct >= 0.98 * len(expected)
    assert elapsed < TIME_LIMIT_SECONDS
