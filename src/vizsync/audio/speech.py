"""Where the speech starts and ends in a recording, with the voice-activity detector that comes
with faster-whisper. No speech model is loaded or downloaded."""

from pathlib import Path

from vizsync.errors import AudioError

_RATE = 16000
_MIN_SILENCE_MS = 300
_MIN_SPEECH_MS = 100

_SNAP_PAD_MS = 30
"""Padding of each stretch of speech used to hold word times to the speech. The library's 400 ms
would leave word starts 0.4 s early."""
_SNAP_MIN_SILENCE_MS = 250
"""Shortest silence that separates two stretches of speech when holding word times to the speech.
Real narrations have about 0.6 s between paragraphs; the library's 2000 ms would merge them."""
_SNAP_MIN_SPEECH_MS = 100


def vad_speech_bounds(path: Path) -> tuple[float, float] | None:
    """Return ``(first speech second, last speech second)`` of a recording, or None if silent.

    Raises:
        AudioError: If the file cannot be decoded.
    """
    segments = _speech_chunks(
        path, min_silence_ms=_MIN_SILENCE_MS, min_speech_ms=_MIN_SPEECH_MS, pad_ms=0
    )
    if not segments:
        return None
    return segments[0][0], segments[-1][1]


def speech_segments(path: Path) -> list[tuple[float, float]]:
    """Return every stretch of speech of a recording as ``(start, end)`` seconds, in order.

    Uses narrow settings (30 ms padding, 250 ms shortest silence), so the pause between two
    paragraphs separates them and a word time can be held to the speech it belongs to.

    Raises:
        AudioError: If the file cannot be decoded.
    """
    return _speech_chunks(
        path,
        min_silence_ms=_SNAP_MIN_SILENCE_MS,
        min_speech_ms=_SNAP_MIN_SPEECH_MS,
        pad_ms=_SNAP_PAD_MS,
    )


def _speech_chunks(
    path: Path, *, min_silence_ms: int, min_speech_ms: int, pad_ms: int
) -> list[tuple[float, float]]:
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    try:
        samples = decode_audio(str(path), sampling_rate=_RATE)
    except Exception as error:
        raise AudioError(f"Cannot read audio ({error})", path=path) from None
    options = VadOptions(
        min_silence_duration_ms=min_silence_ms,
        min_speech_duration_ms=min_speech_ms,
        speech_pad_ms=pad_ms,
    )
    chunks = get_speech_timestamps(samples, options, sampling_rate=_RATE)
    return [(chunk["start"] / _RATE, chunk["end"] / _RATE) for chunk in chunks]
