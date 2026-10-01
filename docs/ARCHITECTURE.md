# Architecture

vizsync finds where each paragraph of a known script sits in a narration recording. This document describes how the code is organized and why.

## Goals

1. **Paragraph-level answers.** Output is start and end per script paragraph, not a transcript.
2. **Robust to imperfect speech recognition.** The script is known, so recognition errors must not move boundaries.
3. **Any recording layout.** One file, several parts, or one file per paragraph give the same output.
4. **Local and free to run.** No account, no upload, no per-use cost.
5. **Easy to test.** The matching logic is pure functions; the speech model is behind an interface and replaced by a fake in tests.
6. **Easy to install.** `pip install vizsync` on Windows and Linux. macOS expected to work, untested.

## Non-goals (v1)

- Producing a transcript for its own sake (many tools already do that).
- Word-level or subtitle output (see roadmap, "Later").
- Editing audio or video.
- Recognizing more than one speaker.

## Stack

| Concern | Choice | Reason |
|---|---|---|
| Language | Python 3.11+ | Same as vizreel; best ecosystem for speech |
| Speech recognition | faster-whisper | Runs on CPU, no separate FFmpeg (bundles PyAV), word timestamps, built-in voice-activity filter |
| Approximate string similarity | rapidfuzz | Fast, standard |
| CLI | Typer | Same as vizreel |
| Data models | Pydantic v2 | Validation and JSON output |
| YAML (chart map) | PyYAML, `safe_load` only | Standard |
| Terminal output | Rich | Same as vizreel |
| Packaging | `pyproject.toml`, `src/` layout, hatchling, uv for development | Same as vizreel |
| Tests | pytest | |
| Lint / format | ruff | |
| Type check | mypy (strict on `script/`, `match/`, `output/`) | Catches errors in data code |

Approved dependencies for v1: `faster-whisper`, `rapidfuzz`, `typer`, `pydantic`, `pyyaml`, `rich`. Dev: `pytest`, `ruff`, `mypy`. Anything else: ask Efe first (candidates: `numpy` for the aligner, `num2words` for number handling).

## Data flow

```
script.md ──► script/parser.py ──► Script (chapters, paragraphs)
                                        │
audio files ──► audio/inputs.py ──► Timeline (parts with offsets)
                                        │
              per-paragraph mode ───────┼──► spans (durations only)
                                        │
              parts mode                ▼
                      asr/ Transcriber ──► Words (text, start, end) on the global timeline
                                        │
                      match/aligner.py ◄┘ (script words vs recognized words)
                                        │
                      match/spans.py ───► ParagraphSpan (start, end, confidence, status)
                                        │
                      pipeline.py runs the steps above ──► AlignmentResult
                      output/ writers ──► timing.json, timing.csv, chapters.txt, markers.edl
                      integrations/vizreel.py ──► chart start/duration
```

## Directory layout

```
vizsync/
├── pyproject.toml
├── README.md
├── CLAUDE.md
├── .claude/agents/algorithm-expert.md
├── docs/  (SPEC.md, ARCHITECTURE.md, ROADMAP.md)
├── examples/
├── scripts/
│   ├── check-local.ps1        ← pulls, then runs check-steps.ps1 (checks Efe runs on Windows)
│   └── check-steps.ps1        ← the checks themselves, one step per check
├── src/vizsync/
│   ├── __init__.py            ← version
│   ├── __main__.py
│   ├── cli.py                 ← Typer app, no business logic
│   ├── errors.py              ← VizsyncError hierarchy
│   ├── pipeline.py            ← script + audio plan → AlignmentResult (no printing, no files)
│   ├── timefmt.py             ← seconds ↔ text
│   ├── script/
│   │   ├── models.py          ← Script, Chapter, Paragraph
│   │   └── parser.py          ← Markdown → Script, collects all errors
│   ├── audio/
│   │   ├── inputs.py          ← expand globs/folders, natural sort, mode detection
│   │   └── timeline.py        ← parts + offsets, durations
│   ├── asr/
│   │   ├── base.py            ← Transcriber protocol, Word model
│   │   └── faster_whisper.py  ← real implementation
│   ├── match/
│   │   ├── normalize.py       ← text → comparable words
│   │   ├── aligner.py         ← script words ↔ recognized words
│   │   └── spans.py           ← alignment → paragraph start/end/confidence
│   ├── output/
│   │   ├── timing.py          ← timing.json models and writer
│   │   ├── table.py           ← csv
│   │   ├── chapters.py        ← chapters.txt
│   │   └── edl.py             ← markers.edl
│   └── integrations/
│       └── vizreel.py         ← chart map → start/duration
└── tests/
    ├── unit/                  ← fast, no model, no audio
    ├── fixtures/              ← short audio clip + matching script
    └── slow/                  ← real model runs, marked `@pytest.mark.slow`
```

## The Transcriber interface

```python
class Word(BaseModel):
    text: str
    start: float   # seconds on the global timeline
    end: float

class Transcriber(Protocol):
    def transcribe(self, audio: Path, *, language: str) -> list[Word]: ...
```

- `FasterWhisperTranscriber` is the only real implementation in v1.
- Tests use a `FakeTranscriber` that returns hand-written words, including deliberate mistakes. This is how the aligner is tested without audio or a model.
- The pipeline calls the transcriber once per audio part and shifts the returned times by the part's offset. Long single files are handled inside faster-whisper (it processes long audio in windows and the voice-activity filter skips silence). The voice-activity filter pads each stretch of speech by 100 ms instead of the library's 400 ms (`DEFAULT_VAD_PARAMETERS`): with 400 ms, paragraph starts moved by up to 0.6 s and differed between a whole clip and the same clip cut into parts.
- The model is downloaded on first use to the standard Hugging Face cache. The tool prints a clear message before a download and a clear error if the download fails.

## The aligner (the hard part)

Input: the script as a list of normalized words, each tagged with its paragraph; the recognized words with times.
Output: for every script word, either the index of the recognized word it matches or "unmatched".

### Normalization (`match/normalize.py`)

Both sides go through the same function: Unicode NFKC, casefold, remove punctuation (keep apostrophes inside words, split on hyphens), split on whitespace. Digits are kept as written.

Details:

- An apostrophe (plain or typographic) is kept only between two letters or digits ("don't", "Northwind's"); elsewhere it is dropped.
- Dashes of every kind and `/` separate words ("twenty-five" gives "twenty", "five").
- A `.` between two digits is a decimal point and is kept ("3.5"). Every other punctuation mark or symbol is removed without separating: "25,000" becomes "25000", "U.S." becomes "us".
- On the recognizer side a word that normalizes to nothing is dropped, and a word that normalizes to several words is split with its time interval shared evenly.

### Alignment

A global sequence alignment (Needleman–Wunsch style dynamic programming) between the two word lists:

- Match score comes from similarity: identical words score highest; near matches (rapidfuzz ratio above a threshold, for example "Zoom" vs "Zume") score positively but lower; dissimilar words are a mismatch with a penalty.
- Skipping a recognized word (recognizer heard extra words) and skipping a script word (narrator skipped it, or recognizer missed it) both cost a gap penalty.
- Global, not local: both sequences are in the same order and cover the same recording, so the whole script maps onto the whole transcript.
- Target size: a 30-minute narration (about 4,500 words) must align in under 10 seconds, excluding speech recognition. A full n×m table is too slow in plain Python at that size.

Implemented in `match/aligner.py` (pure Python plus `rapidfuzz`, no `numpy`):

- Gaps are affine: a run of skipped words pays an opening cost once plus a cost per word, so one long gap (an unspoken paragraph, a hallucination) beats several scattered ones.
- Only a band around the diagonal is computed. It starts `|n − m| + 50` words wide on each side. The best score inside the band is compared with an upper bound on the score of any path that leaves it; if the bound is higher the band is widened and the alignment repeated. The result therefore always has the optimal score of the full table.
- Among equally good alignments, matches are preferred from the end backwards, so when the narrator repeats a sentence the last take is matched.
- Scores (named constants at the top of the module): identical words +2; a near match scores its similarity (rapidfuzz ratio, 0 to 1) when the ratio is at least 0.4; a mismatch −1; a gap costs −1 per skipped word plus −1 per run.
- Measured: 4,500 words with 5% random errors align in about 0.7 s on the development machine.
- The constants were tuned only on synthetic data. The 0.4 similarity threshold is low because "zume"/"zoomy" is 0.44, so short function words ("is"/"in") can near-match each other. They must be re-checked against real recognizer output in M3.

### From alignment to paragraph boundaries (`match/spans.py`)

For each paragraph:

- `start` = start time of its first matched word. `end` = end time of its last matched word.
- If the paragraph's first (or last) script words are unmatched, the boundary would be biased inward. Refinement: move `start` earlier by the number of unmatched leading words times the paragraph's median matched-word duration, but only over recognized words that nothing matched (time where the recognizer heard something the script could not account for). It never moves into silence and never past the matched words of the nearest found neighbour. Same for `end`, moving later. Missing paragraphs are not neighbours; the first and last found paragraphs are bounded by the first and last recognized words. When two neighbours both want the same unmatched words, the room between them is shared in proportion to how far each wanted to move.
- `confidence` = matched script words in the paragraph, weighted by match similarity, divided by total script words in the paragraph.
- `status`: `missing` if fewer than 30% of words matched (or none); `low_confidence` if below `--min-confidence`; otherwise `ok`.
- A `missing` paragraph is never given invented times.

### Known hard cases (must be covered by tests)

| Case | Example | Expected behavior |
|---|---|---|
| Numbers written as words in the script, digits from the recognizer | script "twenty-five thousand dollars", recognizer "25,000 dollars" | Words inside the paragraph may stay unmatched; boundaries stay correct because neighbors match |
| Names misheard | "Zume" heard as "Zoom" or "Zoomy" | Fuzzy match keeps the word matched |
| Narrator skips a sentence | A whole sentence not spoken | Its words are unmatched; paragraph confidence drops; other paragraphs unaffected |
| Narrator repeats a sentence (re-take left in) | Same sentence twice | Alignment picks one occurrence; no crash; a warning if confidence drops |
| Whole paragraph missing from the audio | P17 never spoken | `missing`, neighbors correct |
| Very short paragraph | 3 words | Still gets a span; confidence may be low |
| Recognizer hallucinates text in silence | "Thank you for watching" at the end | Extra words are skipped as gaps |
| Two paragraphs starting with the same words | "And then..." twice | Order constraint keeps them apart |

## Audio inputs (`audio/`)

- `inputs.py` expands folders and wildcards itself (Windows PowerShell does not), natural-sorts folder/wildcard results, detects the mode (see `docs/SPEC.md` §3).
- `timeline.py` reads each part's duration with PyAV (already installed with faster-whisper) and computes offsets: `offset[n] = offset + sum(duration[:n]) + n × gap`.
- In `per-paragraph` mode there is no speech recognition: spans come straight from file durations, laid end to end in script order.

## The pipeline (`pipeline.py`)

`run_alignment` takes the parsed script, an `AudioPlan` (which files, which mode) and a `Transcriber`, and returns an `AlignmentResult`. The CLI builds the plan and the transcriber, shows progress, prints the result and writes the files; the pipeline itself prints nothing and reads files only through the injected `read_duration`. This is why it is tested end to end with `FakeTranscriber`, without audio.

- Parts mode: one `transcribe` call per file, times shifted by the part's offset, one global alignment, `compute_spans`.
- Per-paragraph mode: no recognition; each file is one paragraph, confidence `1.0`; a paragraph without a file is `missing`; files without a paragraph are ignored with a warning.
- Warnings are plain sentences (SPEC §7). Exit code: 2 if any paragraph is missing, else 1 if `--strict` and there are warnings, else 0.
- `faster_whisper.py` imports the library only when a model is needed, so `check` and `--help` stay fast. A failure to load the model raises `ModelLoadError`; the slow tests skip on that error only.

## Outputs

Writers take the same in-memory result object and are independent of each other. Adding a format = one module in `output/` plus a line in `--formats`. The JSON file is the source of truth; every other file can be regenerated from it.

## Errors

- All expected failures raise a subclass of `VizsyncError` with a user-facing message that names the file and line.
- The CLI catches them, prints with Rich, exits with code 1 (or 2 for a `missing` paragraph, see SPEC §2). Unexpected exceptions show a traceback only with `--debug`.
- The script parser collects all problems and reports them together.

## Testing strategy

- `tests/unit/`: parser, normalization, aligner (with `FakeTranscriber`-style word lists including every hard case above), span refinement, time formatting, input expansion, the pipeline, each output writer, chart map. No recorded audio and no model. The only audio is a tiny silent WAV that a few tests write themselves to check the duration reader. These run everywhere, including the cloud environment.
- `tests/slow/`: end-to-end runs with the real model on the fixture clip, marked `@pytest.mark.slow`: the command on the whole clip, the same clip cut into 3 parts (absolute times within 0.3 s), and cut into one file per paragraph (same order, paragraph lengths within 0.3 s; the silences between files are gone, so absolute times cannot match). They skip, with the reason, when the clip or the model is missing. Requires downloading a model, so they run on Efe's computer, not in the cloud environment (network access there is restricted). `VIZSYNC_TEST_MODEL` picks the model (default `base.en`).
- Fixture: `tests/fixtures/northwind.wav`, a 20–35 second PCM WAV of the English lines of `examples/northwind-script.md` with pauses of at least 0.8 s between paragraphs. Efe decides whether it is his own voice or a synthetic voice he generated himself. Never a recording of anyone else.
- The aligner has a benchmark test: 4,500 script words against 4,500 recognized words with 5% random errors finishes under 10 seconds.
- Tests must pass on Windows.

## Cross-platform notes

- `pathlib.Path` everywhere.
- Windows does not expand `*.wav` for Python programs: vizsync does it.
- Output file names are fixed and ASCII.
- CSV is written with a UTF-8 BOM so Excel opens Turkish characters correctly.
- Primary development platform is Windows; CI also runs Ubuntu.
