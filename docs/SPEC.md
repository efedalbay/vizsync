# Specification

This is the source of truth for vizsync's inputs, commands and outputs. If code and this file disagree, fix one of them in the same commit.

## 1. Script format

A script is a Markdown file, saved as UTF-8 (a byte order mark is accepted). Line numbers in messages start at 1.

### Paragraph lines

A paragraph starts with an identifier at the beginning of a line:

```
P12 — Text of the paragraph.
```

- Identifier: `P` followed by digits. `P12`, `P012` and `p12` are the same paragraph, reported as `P12`.
- Separator after the identifier: one of `—`, `–`, `-`, `:`, `.` surrounded by optional spaces. Both `P12 — text` and `P12: text` work.
- Numbers must be unique. They should increase, but gaps are allowed (`P5`, `P7`). A decreasing or repeated number is an error.
- The identifier must be at the very start of the line (no indentation).
- A line that starts with an identifier followed by a space or nothing, but has no separator (`P12 text`), is an error. Otherwise a paragraph would silently swallow it.
- A paragraph's text continues on the following non-blank lines until the next paragraph line, a heading, a blockquote line or a blank line (see below).
- Text that belongs to no paragraph (before the first paragraph, or after a blank line) is ignored.

### What text is aligned (`--text`)

| Mode | Text used for alignment | Use when |
|---|---|---|
| `quote` (default) | The blockquote (`> ...`) lines directly after the paragraph line | Bilingual scripts: the paragraph line holds the reader's language, the quote holds the spoken language |
| `inline` | The text on the paragraph line itself | Single-language scripts |

In `quote` mode a paragraph without a blockquote is an error, reported with its identifier and line number. All blockquote lines that follow a paragraph line, up to the next paragraph line or heading, are joined into one text, even if blank lines separate them. Other text lines are ignored in this mode.

In `inline` mode the text is the paragraph line plus its continuation lines. Blockquote lines are ignored.

Example (`quote` mode):

```markdown
P7 — Birlikte, neredeyse herkesin yaşadığı bir sorunu çözmeye koyuldular. [5]

> Together, they set out to fix something almost everyone has lived through. [5]
```

### Text cleaning before alignment

Applied to the aligned text only:

1. Citation markers like `[5]`, `[30][31]` are removed.
2. Markdown emphasis characters (`*`, `_`, backticks) are removed.
3. HTML comments are removed.
4. Whitespace is collapsed.

A paragraph with no text left after cleaning is an error.

### Headings and chapters

Any Markdown heading of level 2 or 3 (`##`, `###`) starts a chapter. A paragraph belongs to the last chapter heading above it. Paragraphs before the first heading belong to a chapter named `Intro`.

If a heading contains ` / `, the text after the last ` / ` is used as the chapter title when `--text quote` is used, and the text before the first ` / ` when `--text inline` is used. Otherwise the whole heading is used. A leading number and dot (`2. `) is removed.

`## 2. Yükseliş / 2. The Rise` becomes `The Rise` in `quote` mode.

A level 1 heading (`#`) is the document title and is ignored. Headings of level 4 to 6 are ignored too, but they still end the text of the paragraph above.

A heading without paragraphs under it does not create a chapter, and `Intro` exists only if there are paragraphs before the first heading. A heading whose title is empty after the rules above is an error. A script with no paragraphs is an error.

## 2. Commands

Global: `vizsync --version`, `vizsync --help`. All commands accept `--debug` (show tracebacks).

### `vizsync check SCRIPT [--text quote|inline]`

Parses the script only. No audio, no model download. `--text` works as in `align` (default `quote`), because it decides what a valid script is (see §1).

If the script is valid it prints `OK: 3 chapters, 8 paragraphs` and exits with code 0. Otherwise it prints every problem found (all of them, not just the first), one per line as `FILE line N: message`, then `N problems found in FILE`, and exits with code 1. Problems go to standard error.

### `vizsync align AUDIO... --script SCRIPT [options]`

Aligns the script to the audio and writes the output files.

`AUDIO` is one or more files or folders. Wildcards (`*.wav`) are expanded by vizsync itself, because Windows PowerShell does not expand them.

| Option | Default | Meaning |
|---|---|---|
| `--script`, `-s` | required | Script file |
| `--out`, `-o` | `out/` | Output folder |
| `--text` | `quote` | `quote` or `inline` (see §1) |
| `--mode` | `auto` | `auto`, `parts` or `per-paragraph` (see §3) |
| `--model` | `small.en` | Speech model: `tiny.en`, `base.en`, `small.en`, `medium.en`, or another faster-whisper model name or path |
| `--language` | `en` | Language code of the spoken audio |
| `--device` | `auto` | `auto`, `cpu` or `cuda`. `auto` uses the NVIDIA GPU only when it is there and the NVIDIA libraries cuBLAS 12 and cuDNN 9 can be loaded, otherwise the CPU. `cuda` without those libraries is an error |
| `--offset` | `0` | Seconds added to every time (for example a 5 s intro before the narration) |
| `--gap` | `0` | Seconds of silence assumed between consecutive audio parts (`parts` mode) |
| `--min-confidence` | `0.8` | Below this a paragraph is reported as `low_confidence` |
| `--strict` | off | Exit code 1 if any warning was produced |
| `--formats` | `json,csv,chapters,edl` | Comma-separated list of files to write |
| `--fps` | `30` | Frame rate of the video, used for `markers.edl`: `23.976`, `24`, `25`, `29.97`, `30`, `50`, `59.94` or `60`. Anything else is an error (exit code `1`), reported before any listening starts; ignored when `edl` is not in `--formats` |
| `--timeline-start` | `01:00:00:00` | Timecode `HH:MM:SS:FF` where the editor's timeline starts, used for `markers.edl`. DaVinci Resolve starts new timelines at `01:00:00:00` |

Exit codes: `0` success (warnings allowed unless `--strict`), `1` user error (bad script, missing file, invalid option or value, unwritable output folder), `2` alignment finished but at least one paragraph is `missing`. If a paragraph is `missing`, the exit code is `2` even with `--strict`.

What it prints: one line per paragraph (`P3    00:21.9 -> 00:38.0    16.1 s  ok`; a low-confidence line also shows the confidence, a missing one reads `(not found)`), then the count of `ok`, low-confidence and missing paragraphs. Warnings, progress, and in `parts` mode the audio length and the time spent on speech recognition and on matching go to standard error. The first use of a speech model prints a notice that the model is being downloaded. The output folder is created if needed. A wrong option or value is a user error with exit code `1`.

### `vizsync durations TIMING_JSON --map CHART_MAP [--pad SECONDS] [-o FILE]`

Computes chart clip timing for vizreel (see §6). Writes YAML to `-o` or prints it.

## 3. Audio input modes

| Mode | Input | What vizsync does |
|---|---|---|
| `parts` | One or more files in playback order | Concatenates them into one timeline: part 2 starts at `duration(part 1) + gap`, and so on |
| `per-paragraph` | One file per paragraph, name contains the identifier (`P08.wav`, `p8_take2.mp3`) | No speech recognition. Each file is one paragraph; paragraphs are laid end to end in script order |
| `auto` | Anything | If every file name contains a paragraph identifier that exists in the script, `per-paragraph`; otherwise `parts` |

The identifier in a file name is `P` (any case) followed by digits, with no letter or digit directly before the `P` and no digit directly after the number: `P08.wav`, `p8_take2.mp3` and `narration_P3_final.wav` name P8, P8 and P3; `part1.wav` and `xP3.wav` name none. If a name holds several, the first counts.

A single file is `parts` with one part.

Order in `parts` mode: files are sorted by natural order (`part2` before `part10`) when given as a folder or wildcard. Files listed explicitly keep the order given. A folder is read without its subfolders. Folders and wildcards pick up only files with a known audio extension (`.wav`, `.mp3`, `.m4a`, `.flac`, `.ogg`, `.oga`, `.opus`, `.aac`, `.wma`, `.webm`, `.mp4`); a file named in full is accepted with any extension. A named file that does not exist, and a folder or wildcard that finds no audio file, are errors.

Supported audio formats: whatever PyAV can decode (wav, mp3, m4a, flac, ogg, and others).

In `per-paragraph` mode a script paragraph without a file is `missing`. A file with no matching paragraph is ignored, with a warning. Two files for one paragraph are an error. If no file matches any paragraph, that is an error too.

## 4. Time model

- Time zero is the first sample of the first audio part, plus `--offset`.
- All times are seconds as decimal numbers with millisecond precision in JSON, and `MM:SS.s` (or `H:MM:SS.s` above an hour) in text output.
- A paragraph has `start` (first spoken word) and `end` (last spoken word). Silence between paragraphs belongs to neither.

## 5. Output files

All written to the output folder. File names are fixed.

### `timing.json`

```json
{
  "version": 1,
  "tool": "vizsync 0.1.0",
  "script": "northwind.md",
  "mode": "parts",
  "offset": 0.0,
  "total_duration": 71.4,
  "audio": [
    { "file": "part1.wav", "offset": 0.0, "duration": 38.2 },
    { "file": "part2.wav", "offset": 38.2, "duration": 33.2 }
  ],
  "chapters": [
    { "title": "The Hook", "start": 0.4, "end": 21.1, "first": "P1", "last": "P2" }
  ],
  "paragraphs": [
    {
      "id": "P1",
      "chapter": "The Hook",
      "start": 0.4,
      "end": 9.8,
      "duration": 9.4,
      "confidence": 0.98,
      "status": "ok"
    }
  ],
  "warnings": []
}
```

`status` is one of `ok`, `low_confidence`, `missing`. A `missing` paragraph has `start`, `end` and `duration` set to `null`.

Details:

- `mode` is `parts` or `per-paragraph` (the mode actually used, never `auto`).
- `audio` lists the files by file name only. In `parts` mode they are in playback order; in `per-paragraph` mode, in script order. `offset` is where the file starts on the timeline, so it includes `--offset`. `total_duration` is the length of the audio (durations plus gaps) and does not include `--offset`.
- `paragraphs` are in script order and `chapters` in script order. A chapter's `first` and `last` are the identifiers of its first and last paragraph in the script, whether or not they are missing.
- All times, `duration` and `confidence` are rounded to three decimals. In `per-paragraph` mode `confidence` is `1.0` for a paragraph with a file and `0.0` for one without.
- The file is UTF-8 (no byte order mark), indented by two spaces, and ends with a newline.

A chapter's `start` is the `start` of its first paragraph that is not `missing`; its `end` is the `end` of its last such paragraph.

### `timing.csv`

Header: `id,chapter,start,end,duration,confidence,status`. One row per paragraph, in script order, with the same values as in `timing.json`. Times in seconds. UTF-8 with BOM (so Excel on Windows opens it correctly). Empty cells for `null`. Cells with commas or quotes are quoted.

### `chapters.txt`

YouTube description format, one line per chapter: `MM:SS Title`. If the video lasts an hour or more, every line uses `H:MM:SS` instead (`0:00:00 Title`). The title is the chapter title of the script (the same one as in `timing.json`). The file is UTF-8, ends with a newline, and holds the lines only. Rules applied:

- The first chapter is written at `00:00` (YouTube requires it), even if narration starts later. If the real start is more than 1 s after zero, a warning says so: `chapters: 'The Hook' starts at 00:04 but YouTube needs the first chapter at 00:00; it is written at 00:00.`
- Times are rounded down to whole seconds. They include `--offset`.
- A chapter whose paragraphs are all `missing` is left out, with a warning: `chapters: 'The Fall' skipped, none of its paragraphs was found.` The first chapter that is left is the one written at `00:00`. If no chapter is left, the file is not written.
- Warnings when fewer than 3 chapters are listed (`chapters: only 2 chapters, YouTube needs at least 3.`) or a chapter is shorter than 10 s (`chapters: 'The Hook' is only 6 s long, YouTube needs at least 10 s.`). YouTube ignores the list in those cases. A chapter lasts until the next listed chapter starts; the last one lasts until the end of the video (`--offset` plus `total_duration`).

These warnings are added only when `chapters` is in `--formats`, and they are stored in `timing.json` like any other warning.

### `markers.edl`

An EDL file that DaVinci Resolve imports as timeline markers (Timeline → Import → Timeline Markers from EDL). One marker per paragraph that was found, named with the identifier, at the paragraph `start`, one frame long, in the order of the script. A `missing` paragraph has no marker.

```
TITLE: northwind
FCM: NON-DROP FRAME

001  001      V     C        01:00:00:12 01:00:00:13 01:00:00:12 01:00:00:13  
 |C:ResolveColorBlue |M:P1 |D:1
```

- `TITLE` is the script file name without its extension.
- Timecodes are `HH:MM:SS:FF` and start at `--timeline-start`. The frame is the nearest one to the paragraph start. Frames are counted at the real frame rate (29.97 counts 29.97 per second) and written at the nominal one (30); drop-frame timecode is not supported.
- Lines end with `\n`, the file is UTF-8 and ends with a newline.

Resolve places a marker by the record timecode of its event, so the timeline's start matters: if the timeline in Resolve starts at 00:00:00:00, pass `--timeline-start 00:00:00:00`. Import into Resolve is not verified yet (see `docs/ROADMAP.md`, M4).

## 6. Chart timing for vizreel

`vizsync durations` reads `timing.json` and a chart map, and reports when each chart clip goes on the timeline and how long it must be. It is written against vizreel 0.11 (`docs/SPEC.md` there is the source of truth for `duration`, `step_duration` and sequences). vizreel still takes chart timing from the YAML spec; CSV files in vizreel only carry a chart's data (bars, series, events), not its timing.

### Chart map

```yaml
version: 1
charts:
  peak-valuation:            # a single clip
    paragraphs: [P2]
  valuation:                 # one clip covering two paragraphs
    paragraphs: [P3, P4]
  history:                   # a vizreel sequence: one clip per paragraph, in order
    sequence: true
    paragraphs: [P6, P7, P8]
```

- The key is the vizreel chart `id`.
- `paragraphs` lists one or more paragraph identifiers. They must be consecutive in the script.
- With `sequence: true`, each paragraph is one clip of the sequence, in the order listed (vizreel allows 2–8 clips).
- Unknown identifiers or `missing` paragraphs are errors.

### Result

```yaml
charts:
  peak-valuation:
    start: 10.6
    duration: 10.5
  valuation:
    start: 21.9
    duration: 27.6
  history:
    start: 62.0
    duration: 14.1          # first clip: goes into `duration`
    step_duration: 12.6     # longest later clip: goes into `step_duration`
    clips:
      - { n: 1, start: 62.0, duration: 14.1 }
      - { n: 2, start: 76.1, duration: 13.4 }
      - { n: 3, start: 89.5, duration: 12.6 }
```

Single clip: `start` = start of the first paragraph (where to place the clip in the editor). `duration` = end of the last paragraph minus that start, plus `--pad` (default `0`).

Sequence: clips are cut back to back, so clip *k* runs from the start of paragraph *k* to the start of paragraph *k+1* (no gap on the timeline); the last clip runs to the end of its paragraph plus `--pad`. `duration` is the first clip's length. vizreel has one `step_duration` for all later clips, so vizsync reports the longest later clip: a clip can be trimmed in the editor (it holds its last frame) but not made longer than it was rendered. The exact per-clip times are in `clips`.

Warnings: a clip shorter than 2 seconds (vizreel's minimum `duration`); for sequences, a later clip much shorter than the reported `step_duration`.

Values are in seconds and go into the vizreel spec's `duration:` / `step_duration:` fields.

vizsync never edits a vizreel spec file itself, because rewriting YAML with a standard library drops the comments that scripts rely on for fact references.

## 7. Warnings

Each warning is a short sentence with the identifier. Examples: `P17: low confidence (0.62). The narration may differ from the script.`, `P23: not found in the audio.` (`parts` mode) or `P23: no audio file.` (`per-paragraph` mode), `notes.wav: matches no paragraph of the script, ignored.`, `P4: 730.8 s for 12 words, much longer than the other paragraphs. The script may be read more than once or out of order.` (`parts` mode: a found paragraph whose seconds per word exceed 3 times the median of all found paragraphs, at least 5 s long, needs 3 or more found paragraphs; its status stays `ok`), `chapters: only 2 chapters, YouTube needs at least 3.` Warnings are printed and stored in `timing.json`.

## 8. Errors

Expected failures print a message a user can act on and exit with code 1. Examples: `Script line 41: P9 has no blockquote (use --text inline?)`, `Audio file not found: part3.wav`. Messages name the file and line whenever possible.
