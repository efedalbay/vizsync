"""Where the speech starts and ends in a recording, with the voice-activity detector that comes
with faster-whisper. No speech model is loaded or downloaded."""

from pathlib import Path

from vizsync.errors import AudioError

_RATE = 16000
_MIN_SILENCE_MS = 300
_MIN_SPEECH_MS = 100


def vad_speech_bounds(path: Path) -> tuple[float, float] | None:
    """Return ``(first speech second, last speech second)`` of a recording, or None if silent.

    Raises:
        AudioError: If the file cannot be decoded.
    """
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    try:
        samples = decode_audio(str(path), sampling_rate=_RATE)
    except Exception as error:
        raise AudioError(f"Cannot read audio ({error})", path=path) from None
    options = VadOptions(
        min_silence_duration_ms=_MIN_SILENCE_MS,
        min_speech_duration_ms=_MIN_SPEECH_MS,
        speech_pad_ms=0,
    )
    chunks = get_speech_timestamps(samples, options, sampling_rate=_RATE)
    if not chunks:
        return None
    return chunks[0]["start"] / _RATE, chunks[-1]["end"] / _RATE
