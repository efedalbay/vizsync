# Roadmap

Work proceeds one milestone at a time. A milestone is done only when every acceptance criterion is met, tests pass on Windows, and the relevant docs are updated.

## M0 — Project skeleton

- `pyproject.toml` with `src/` layout, package name `vizsync`, Python `>=3.11`, entry point `vizsync = vizsync.cli:app`.
- Dependencies: `typer`, `pydantic>=2`, `pyyaml`, `rich`. Dev: `pytest`, `ruff`, `mypy`. (Speech and matching dependencies are added in the milestones that need them.)
- `vizsync --version` and `vizsync --help` work.
- `errors.py` with the `VizsyncError` hierarchy; `timefmt.py` with tests.
- ruff, mypy and pytest configured in `pyproject.toml`; `slow` marker registered.
- GitHub Actions: lint + unit tests on `windows-latest` and `ubuntu-latest`, Python 3.11 and 3.12.

**Done when:** `uv sync` then `uv run vizsync --version` works on Windows; CI is green.

## M1 — Script parser and `check`

- Models and parser exactly as in `docs/SPEC.md` §1 (both `--text` modes, chapters, heading title rules, cleaning, all error cases, all errors reported together).
- `vizsync check SCRIPT`.
- `examples/northwind-script.md` (already present) parses; a set of broken scripts in `tests/unit/fixtures/` produce the expected messages with line numbers.

**Done when:** every rule in SPEC §1 has a test; `vizsync check examples/northwind-script.md` reports 3 chapters and 8 paragraphs.

## M2 — Normalization and aligner (pure logic)

**This is the milestone for the `algorithm-expert` subagent** (see `CLAUDE.md`).

- `Word`/`Transcriber` models in `asr/base.py`; `FakeTranscriber` helper for tests.
- `match/normalize.py`, `match/aligner.py`, `match/spans.py` as in `docs/ARCHITECTURE.md`.
- Tests for every row of the "Known hard cases" table, written before the implementation.
- Benchmark test: 4,500 words, 5% random errors, under 10 seconds.

**Done when:** all hard-case tests and the benchmark pass; no audio or model is used anywhere in the tests.

## M3 — Real audio: `align` end to end

- `audio/inputs.py`, `audio/timeline.py`: single file, parts, per-paragraph, wildcard/folder expansion, natural sort, mode detection.
- `asr/faster_whisper.py`: model loading, download message, device selection, word timestamps.
- `vizsync align` producing `timing.json` and `timing.csv`, with warnings, exit codes and `--strict`.
- Slow end-to-end test on the fixture clip.
- Measure and record in the README: time to align a ~13-minute narration on a typical Windows laptop CPU with `small.en`.

**Done when:** the fixture clip aligns with every paragraph `ok`; the same audio split into 3 parts gives the same paragraph times within 0.3 s, and split into per-paragraph files gives the same paragraph order and the same paragraph lengths within 0.3 s (the silences between files are gone, so absolute times cannot match).

## M4 — Chapters and editor markers

- `chapters.txt` with the YouTube rules from SPEC §5 and their warnings.
- `markers.edl` and `--fps`.
- Import `markers.edl` into DaVinci Resolve on Windows and confirm the markers land on the right frames. If Resolve needs a different EDL dialect, adjust and document. Document what to do in CapCut (no marker import known: list the times instead).

**Done when:** markers verified in Resolve by Efe and the README explains the steps.

## M5 — vizreel chart timing

- Before starting, read vizreel's current `docs/SPEC.md` (fields `duration`, `step_duration`, Sequences) and adjust `docs/SPEC.md` §6 if vizreel changed.
- Chart map model and validation, including `sequence: true`.
- `vizsync durations` as in SPEC §6: single clips, sequences with per-clip times, and the warnings.
- `examples/chart-map.yaml` works with `examples/timing.example.json`.
- README section showing the full flow: script → audio → `align` → `durations` → vizreel spec.

**Done when:** the flow on the example produces chart `start`/`duration` (and `clips` for a sequence) that match a hand calculation from `timing.json`.

## M6 — Release v0.1.0

- README finished with real command output and the measured speed.
- `pip install vizsync` in a clean environment works on Windows and Ubuntu.
- PyPI trusted publishing via GitHub Actions (same setup as vizreel).
- GitHub release with notes.

**Done when:** `pip install vizsync` then `vizsync align` on the example works in a fresh virtual environment.

## Later

- Subtitle output (SRT/VTT) from word times.
- Word-level export in `timing.json`.
- Number normalization ("25,000" ↔ "twenty-five thousand") for higher confidence.
- Script tags such as `<!-- chart: valuation -->` instead of a separate chart map.
- Other recognition backends (whisper.cpp, a hosted API) behind the `Transcriber` interface.
- Other languages beyond English narration.
- `--patch` for vizreel specs using a comment-preserving YAML library.
- macOS testing.
