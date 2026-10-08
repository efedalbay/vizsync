"""From script and audio to timed paragraphs. Orchestrates the pure parts; prints nothing."""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from vizsync.asr.base import Transcriber, Word
from vizsync.audio.inputs import AudioMode, AudioPlan, paragraph_id_in_name
from vizsync.audio.join import JoinLayout, SpeechBounds, plan_join
from vizsync.audio.timeline import Part, build_timeline, read_duration, total_duration
from vizsync.errors import AudioError
from vizsync.match.normalize import normalize_text
from vizsync.match.pace import Pace, slow_paragraphs
from vizsync.match.spans import (
    DEFAULT_MIN_CONFIDENCE,
    ParagraphSpan,
    ParagraphStatus,
    compute_spans,
)
from vizsync.script.models import Script


@dataclass(frozen=True)
class ParagraphResult:
    """Where one paragraph is. ``start`` and ``end`` are None when it is missing."""

    id: str
    chapter: str
    start: float | None
    end: float | None
    confidence: float
    status: ParagraphStatus
    text: str = ""
    """The text that was aligned (cleaned), for captions."""
    word_times: tuple[tuple[float, float] | None, ...] = field(default=(), compare=False)
    """See ``ParagraphSpan.word_times``."""


@dataclass(frozen=True)
class ChapterResult:
    """A chapter. ``start``/``end`` come from its first and last paragraph that is not missing."""

    title: str
    first: str
    last: str
    start: float | None
    end: float | None


@dataclass(frozen=True)
class AlignmentResult:
    """Everything the output files and the console summary are built from."""

    script_name: str
    mode: AudioMode
    offset: float
    total_duration: float
    parts: list[Part]
    chapters: list[ChapterResult]
    paragraphs: list[ParagraphResult]
    warnings: list[str]
    transcription_seconds: float
    matching_seconds: float


def run_alignment(
    script: Script,
    script_name: str,
    plan: AudioPlan,
    *,
    transcriber: Transcriber | None,
    language: str = "en",
    offset: float = 0.0,
    gap: float = 0.0,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    read_duration: Callable[[Path], float] = read_duration,
    on_progress: Callable[[str], None] | None = None,
    joined: JoinLayout | None = None,
) -> AlignmentResult:
    """Find every paragraph of ``script`` in the audio described by ``plan``.

    In parts mode the transcriber listens to each file, the words are moved onto one timeline
    and matched against the script. In per-paragraph mode nothing is recognized: the files are
    laid end to end in script order and each file is one paragraph.

    Args:
        script: The parsed script.
        script_name: The script file name, stored in the result.
        plan: Which files to use and in which mode (see ``plan_audio``).
        transcriber: Needed in parts mode.
        language: Language of the spoken audio.
        offset: Seconds added to every time.
        gap: Seconds of silence assumed between consecutive parts (parts mode only).
        min_confidence: Below this a found paragraph is ``low_confidence``.
        read_duration: How to measure a file; replaceable so tests need no audio.
        on_progress: Called with a short message before each slow step.
        joined: In per-paragraph mode, where each paragraph goes in a joined narration file (see
            ``plan_narration``). The times are then those of that file, silences included.
    """
    settings = _Settings(
        language=language,
        offset=offset,
        gap=gap,
        min_confidence=min_confidence,
        measure=read_duration,
        progress=on_progress or (lambda message: None),
    )
    if plan.mode is AudioMode.PARTS:
        if transcriber is None:
            raise ValueError("parts mode needs a transcriber")
        outcome = _align_parts(script, plan, transcriber, settings)
    elif joined is not None:
        outcome = _align_joined(script, plan, joined, settings)
    else:
        outcome = _align_paragraph_files(script, plan, settings)
    return _assemble(script, script_name, settings.offset, outcome)


def exit_code(result: AlignmentResult, *, strict: bool) -> int:
    """2 if any paragraph is missing, else 1 if ``strict`` and there are warnings, else 0."""
    if any(p.status is ParagraphStatus.MISSING for p in result.paragraphs):
        return 2
    if strict and result.warnings:
        return 1
    return 0


@dataclass(frozen=True)
class _Settings:
    language: str
    offset: float
    gap: float
    min_confidence: float
    measure: Callable[[Path], float]
    progress: Callable[[str], None]


@dataclass(frozen=True)
class _Outcome:
    """What a mode found, before it is arranged by chapter."""

    mode: AudioMode
    total_duration: float
    parts: list[Part]
    spans: list[ParagraphSpan]
    leading_warnings: list[str]
    missing_reason: str
    transcription_seconds: float = 0.0
    matching_seconds: float = 0.0


def _align_parts(
    script: Script, plan: AudioPlan, transcriber: Transcriber, settings: _Settings
) -> _Outcome:
    durations = [settings.measure(path) for path in plan.files]
    parts = build_timeline(plan.files, durations, gap=settings.gap, offset=settings.offset)
    started = time.perf_counter()
    words: list[Word] = []
    for index, part in enumerate(parts, start=1):
        settings.progress(f"Listening to {part.file.name} ({index}/{len(parts)})")
        heard = transcriber.transcribe(part.file, language=settings.language)
        words.extend(_shifted(heard, part.offset))
    transcribed = time.perf_counter()
    settings.progress("Matching the script to the words")
    spans = compute_spans(script.paragraphs, words, min_confidence=settings.min_confidence)
    matched = time.perf_counter()
    return _Outcome(
        mode=AudioMode.PARTS,
        total_duration=total_duration(durations, gap=settings.gap),
        parts=parts,
        spans=spans,
        leading_warnings=[],
        missing_reason="not found in the audio.",
        transcription_seconds=transcribed - started,
        matching_seconds=matched - transcribed,
    )


def _align_paragraph_files(script: Script, plan: AudioPlan, settings: _Settings) -> _Outcome:
    files = list(plan.paragraph_files.values())
    settings.progress("Measuring the audio files")
    durations = [settings.measure(path) for path in files]
    parts = build_timeline(files, durations, offset=settings.offset)
    part_of = dict(zip(plan.paragraph_files, parts, strict=True))
    return _Outcome(
        mode=AudioMode.PER_PARAGRAPH,
        total_duration=total_duration(durations),
        parts=parts,
        spans=[_span_of_file(p.id, part_of.get(p.id)) for p in script.paragraphs],
        leading_warnings=[
            f"{path.name}: matches no paragraph of the script, ignored." for path in plan.ignored
        ],
        missing_reason="no audio file.",
    )


def plan_narration(
    script: Script,
    plan: AudioPlan,
    *,
    target: Path,
    paragraph_gap: float,
    chapter_gap: float,
    speech_bounds: SpeechBounds | None = None,
) -> JoinLayout:
    """Plan the joined narration of a per-paragraph recording (see ``audio.join``).

    Raises:
        AudioError: If the recording is not one file per paragraph, or the files cannot be joined.
    """
    if plan.mode is not AudioMode.PER_PARAGRAPH:
        raise AudioError(_join_needs_paragraph_files(script, plan))
    paragraphs = [
        (paragraph.id, number)
        for number, chapter in enumerate(script.chapters)
        for paragraph in chapter.paragraphs
    ]
    return plan_join(
        paragraphs,
        plan.paragraph_files,
        target=target,
        paragraph_gap=paragraph_gap,
        chapter_gap=chapter_gap,
        speech_bounds=speech_bounds,
    )


def _join_needs_paragraph_files(script: Script, plan: AudioPlan) -> str:
    known = {paragraph.id for paragraph in script.paragraphs}
    unmatched = [path.name for path in plan.files if paragraph_id_in_name(path) not in known]
    if not unmatched:
        return (
            "--join needs one file per paragraph, but these files are read as parts of one "
            "recording (--mode parts)."
        )
    one = len(unmatched) == 1
    return (
        f"--join needs one file per paragraph, named like {script.paragraphs[0].id}.wav, but "
        f"{', '.join(unmatched)} {'matches' if one else 'match'} no paragraph of the script. "
        f"Rename {'it' if one else 'them'}, or pass --mode per-paragraph to ignore "
        f"{'it' if one else 'them'}."
    )


def _align_joined(
    script: Script, plan: AudioPlan, joined: JoinLayout, settings: _Settings
) -> _Outcome:
    rate = joined.format.frame_rate
    by_id = {entry.paragraph_id: entry for entry in joined.entries}
    spans = []
    for paragraph in script.paragraphs:
        paragraph_id = paragraph.id
        entry = by_id.get(paragraph_id)
        if entry is None:
            spans.append(ParagraphSpan(paragraph_id, None, None, 0.0, ParagraphStatus.MISSING))
            continue
        start = settings.offset + entry.offset_frames / rate
        end = settings.offset + (entry.offset_frames + entry.frames) / rate
        spans.append(ParagraphSpan(paragraph_id, start, end, 1.0, ParagraphStatus.OK))
    return _Outcome(
        mode=AudioMode.PER_PARAGRAPH,
        total_duration=joined.total_seconds,
        parts=[Part(joined.target, settings.offset, joined.total_seconds)],
        spans=spans,
        leading_warnings=[
            f"{path.name}: matches no paragraph of the script, ignored." for path in plan.ignored
        ]
        + joined.warnings,
        missing_reason="no audio file.",
    )


def _span_of_file(paragraph_id: str, part: Part | None) -> ParagraphSpan:
    if part is None:
        return ParagraphSpan(paragraph_id, None, None, 0.0, ParagraphStatus.MISSING)
    return ParagraphSpan(
        paragraph_id, part.offset, part.offset + part.duration, 1.0, ParagraphStatus.OK
    )


def _shifted(words: Sequence[Word], offset: float) -> list[Word]:
    return [Word(text=w.text, start=w.start + offset, end=w.end + offset) for w in words]


def _assemble(
    script: Script, script_name: str, offset: float, outcome: _Outcome
) -> AlignmentResult:
    span_of = {span.id: span for span in outcome.spans}
    paragraphs = [
        ParagraphResult(
            id=paragraph.id,
            chapter=chapter.title,
            start=span_of[paragraph.id].start,
            end=span_of[paragraph.id].end,
            confidence=span_of[paragraph.id].confidence,
            status=span_of[paragraph.id].status,
            text=paragraph.text,
            word_times=span_of[paragraph.id].word_times,
        )
        for chapter in script.chapters
        for paragraph in chapter.paragraphs
    ]
    chapters = [
        _chapter_result(
            chapter.title, chapter.paragraphs[0].id, chapter.paragraphs[-1].id, paragraphs
        )
        for chapter in script.chapters
    ]
    return AlignmentResult(
        script_name=script_name,
        mode=outcome.mode,
        offset=offset,
        total_duration=outcome.total_duration,
        parts=outcome.parts,
        chapters=chapters,
        paragraphs=paragraphs,
        warnings=outcome.leading_warnings
        + _paragraph_warnings(
            paragraphs,
            outcome.missing_reason,
            _word_counts(script) if outcome.mode is AudioMode.PARTS else {},
        ),
        transcription_seconds=outcome.transcription_seconds,
        matching_seconds=outcome.matching_seconds,
    )


def _chapter_result(
    title: str, first: str, last: str, paragraphs: Sequence[ParagraphResult]
) -> ChapterResult:
    ids = [p.id for p in paragraphs]
    members = paragraphs[ids.index(first) : ids.index(last) + 1]
    found = [p for p in members if p.start is not None and p.end is not None]
    if not found:
        return ChapterResult(title, first, last, None, None)
    return ChapterResult(title, first, last, found[0].start, found[-1].end)


def _word_counts(script: Script) -> dict[str, int]:
    return {p.id: len(normalize_text(p.text)) for p in script.paragraphs}


def _paragraph_warnings(
    paragraphs: Sequence[ParagraphResult], missing_reason: str, word_counts: dict[str, int]
) -> list[str]:
    slow = _slow_paragraphs(paragraphs, word_counts)
    warnings: list[str] = []
    for paragraph in paragraphs:
        if paragraph.status is ParagraphStatus.MISSING:
            warnings.append(f"{paragraph.id}: {missing_reason}")
            continue
        if paragraph.status is ParagraphStatus.LOW_CONFIDENCE:
            warnings.append(
                f"{paragraph.id}: low confidence ({paragraph.confidence:.2f}). "
                "The narration may differ from the script."
            )
        if paragraph.id in slow and paragraph.start is not None and paragraph.end is not None:
            warnings.append(
                f"{paragraph.id}: {paragraph.end - paragraph.start:.1f} s for "
                f"{word_counts[paragraph.id]} words, much longer than the other paragraphs. "
                "The script may be read more than once or out of order."
            )
    return warnings


def _slow_paragraphs(
    paragraphs: Sequence[ParagraphResult], word_counts: dict[str, int]
) -> set[str]:
    paces = [
        Pace(p.id, word_counts[p.id], p.end - p.start)
        for p in paragraphs
        if p.start is not None and p.end is not None and p.id in word_counts
    ]
    return set(slow_paragraphs(paces))
