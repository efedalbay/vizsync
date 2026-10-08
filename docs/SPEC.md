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
- The identifier may be written in bold or italics: `**P12** — text`, `*P12* — text` and `__P12__ — text` are the same paragraph as `P12 — text`. The opening and closing marks must be the same (`**P12*` is not a paragraph line). The separator follows the closing mark.
- Separator after the identifier: one of `—`, `–`, `-`, `:`, `.` surrounded by optional spaces. Both `P12 — text` and `P12: text` work.
- Numbers must be unique. They should increase, but gaps are allowed (`P5`, `P7`). A decreasing or repeated number is an error.
- The identifier (with its emphasis marks, if any) must be at the very start of the line (no indentation).
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

### Chart tags

A paragraph can say which vizreel chart it is part of, with an HTML comment anywhere in the paragraph, usually on its own line below the text (see §6):

```markdown
P7 — ...

> ...

<!-- chart: bet-size -->
```

- `<!-- chart: ID -->` ties the paragraph to the chart `ID` (lowercase letters, digits and `-`). `<!-- chart: ID, sequence -->` also says that the chart is a sequence (one clip per paragraph). Spaces and letter case around `chart`, `:` and `,` do not matter.
- The tag belongs to the paragraph it is under: from the paragraph line to the next paragraph line or heading, whether or not blank lines or the blockquote come in between. A paragraph may have several tags (it is then part of several charts), but not the same chart twice.
- A tag on a heading, before the first paragraph, or after a heading and before the next paragraph is an error: `the chart tag is not under a paragraph`. So is a tag with no id or with more than one option (`invalid chart tag`), an id with a character that is not allowed, and an option other than `sequence`. All are reported with their line like any other script problem.
- Other HTML comments are left alone. A tag is removed from the aligned text like every comment, so it never affects alignment, but a comment that merely quotes the tag syntax, for example in the header of a script, is read as a tag too.

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

Text output (paths, titles, messages) is written as UTF-8 whenever standard output or standard error is not a terminal, that is when it is redirected to a file or a pipe or captured by another program. Python would otherwise use the legacy code page of the system (cp1254 on a Turkish Windows), and a reader that expects UTF-8 would show a path such as `ledgerfall-kitaplık` as a replacement character. In a terminal the console's own encoding is used. A character the output cannot show is replaced, never an error. In Windows PowerShell 5.1, pipe vizsync into another program only after `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`.

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
| `--join` | off | Only for one file per paragraph. Also writes `narration.wav`, the files joined into one with silence between them, and gives the times of that file (see §3) |
| `--paragraph-gap` | `0.6` | With `--join`: seconds of silence between two paragraphs of a chapter |
| `--chapter-gap` | `1.2` | With `--join`: seconds of silence where a new chapter begins |
| `--trim` | off | With `--join`: first cut the silence at the start and end of every file (see §3) |
| `--formats` | `json,csv,chapters,edl,srt` | Comma-separated list of files to write |
| `--fps` | `30` | Frame rate of the video, used for `markers.edl`: `23.976`, `24`, `25`, `29.97`, `30`, `50`, `59.94` or `60`. Anything else is an error (exit code `1`), reported before any listening starts; ignored when `edl` is not in `--formats` |
| `--timeline-start` | `01:00:00:00` | Timecode `HH:MM:SS:FF` where the editor's timeline starts, used for `markers.edl`. DaVinci Resolve starts new timelines at `01:00:00:00` |

Exit codes: `0` success (warnings allowed unless `--strict`), `1` user error (bad script, missing file, invalid option or value, unwritable output folder), `2` alignment finished but at least one paragraph is `missing`. If a paragraph is `missing`, the exit code is `2` even with `--strict`.

What it prints: one line per paragraph (`P3    00:21.9 -> 00:38.0    16.1 s  ok`; a low-confidence line also shows the confidence, a missing one reads `(not found)`), then the count of `ok`, low-confidence and missing paragraphs. Warnings, progress, and in `parts` mode the audio length and the time spent on speech recognition and on matching go to standard error. The first use of a speech model prints a notice that the model is being downloaded. The output folder is created if needed. A wrong option or value is a user error with exit code `1`.

### `vizsync durations TIMING_JSON [--map CHART_MAP] [--script SCRIPT [--text quote|inline]] [--pad SECONDS] [-o FILE]`

Computes chart clip timing for vizreel (see §6). The charts come from a chart map (`--map`), from the chart tags of the script (`--script`, see §1), or from both together; at least one is needed, and a chart that is in both is an error. `--text` is needed only to parse the script (default `quote`). Writes YAML to `-o` or prints it. `--pad` (default `0`, not negative) adds seconds to the end of a clip.

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

### Joining the paragraph files (`--join`)

Without `--join`, `per-paragraph` mode only reports the order and the length of each paragraph, because the silence between the files is gone and absolute times are not known. With `--join`, vizsync lays the files one after the other into `narration.wav` in the output folder, with silence between them, and the times of `timing.json` (and of every other output file) are those of that file.

- The order is the order of the script. A paragraph without a file is `missing` and has no silence of its own.
- Between two paragraphs of a chapter there is `--paragraph-gap` seconds of silence (default 0.6); where a new chapter begins, `--chapter-gap` seconds (default 1.2), measured against the last paragraph that has a file. There is no silence before the first paragraph or after the last.
- The samples of a plain PCM WAV file are copied unchanged: nothing is resampled or encoded again, and only silence is added. An MP3 file (text-to-speech services such as ElevenLabs give MP3) is decoded once to 16-bit PCM at its own sample rate and channel count, and those samples are written, so no second lossy generation is made; the MP3 file itself is not touched. Other compressed formats (M4A, Ogg, ...) and other kinds of WAV (float, 24-bit, extensible) are refused with a message that says to convert them. WAV and MP3 files can be mixed. All files must have the same sample rate, channel count and sample size once decoded (an MP3 is always 16-bit); otherwise the run stops with a message naming the two files and their formats, before anything is written. Sample rates and channel counts are never converted.
- A gap is rounded to a whole number of samples, and every time is computed from sample counts (for an MP3, the number of samples it decodes to), so a time in `timing.json` is a sample position of `narration.wav`: its length is the sum of the paragraph lengths and the gaps, to the sample (`total_duration` is that length, rounded like any time).
- `--trim` cuts the silence at the start and end of each file before joining, so the gaps sound equal even when the files carry silences of different lengths. It uses the voice-activity detector that comes with faster-whisper (no speech model is needed) and keeps 0.05 s before the first and after the last speech. Only whole samples are cut, nothing else changes. A file in which no speech is found is joined whole, with a warning (`P3.wav: no speech found, not trimmed.`).
- `--paragraph-gap`, `--chapter-gap` and `--trim` without `--join` are errors, and so is `--join` with a recording that is not one file per paragraph. Both stop the run before anything is done. `--offset` still shifts every time but not the file.
- `timing.json` has `mode` `per-paragraph` and one entry in `audio`: `narration.wav`.
- The file is written to a temporary name and renamed, so a failed run never leaves a half-written `narration.wav`. An existing `narration.wav` is replaced.

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
- `audio` lists the files by file name only. In `parts` mode they are in playback order; in `per-paragraph` mode, in script order, or just `narration.wav` with `--join`. `offset` is where the file starts on the timeline, so it includes `--offset`. `total_duration` is the length of the audio (durations plus gaps) and does not include `--offset`.
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

### `captions.srt`

The script text as subtitles (SubRip), timed by the speech. The text is the aligned text of each paragraph (`--text`), already without source marks such as `[5]`, so it is what the script says and not what a recognizer heard. A paragraph that is `missing` has no cue. The file is UTF-8 without a byte order mark, uses `\n` line ends and ends with a newline; times are `HH:MM:SS,mmm`, cues are numbered from 1 and separated by a blank line. If there is no cue at all, the file is not written.

Cues:

- A cue is a sentence, or a part of a long one (a sentence ends at `.`, `!`, `?` or `…`, with closing quotes or brackets). A cue has at most 2 lines of at most 42 characters; a line break falls between words, as evenly as the lines allow. A word longer than a line is kept whole.
- A sentence that does not fit in two lines is cut after a comma, semicolon, colon or dash when both parts keep at least a fifth of its length, otherwise as evenly as possible between words. The parts are cut again until each fits.
- A cue lasts at most 7 s: a longer one is cut the same way, at the point nearest to its middle in time.
- A cue starts when its first word was spoken and ends when its last was, using the times of the words the aligner matched. A script word that matched no recognized word, and every word of a paragraph that was never recognized (`per-paragraph` files, with or without `--join`), is placed between the nearest known times (or the start and end of the paragraph) in proportion to its length. The first cue of a paragraph starts at the paragraph's `start` and the last ends at its `end`.
- A cue shorter than 1 s is made one second long, in this order: lengthened into the free time after it (never into a cue of the next paragraph); joined to the neighbouring cue of its paragraph when the joined text still fits two lines and lasts at most 7 s (the shorter neighbour is chosen); given time from the next cue of its paragraph, which then starts later, while that cue stays at least 1 s long. The last cue of the file may run past the end of its paragraph. A cue stays shorter than a second only when none of these is possible, for example a paragraph of one short word followed at once by the next paragraph. Cues never overlap: a cue is cut short where the next begins.
- Times include `--offset`, as everywhere else.

## 6. Chart timing for vizreel

`vizsync durations` reads `timing.json` and a chart map, and reports when each chart clip goes on the timeline and how long it must be. It is written against vizreel 0.16 (`docs/SPEC.md` there is the source of truth for `duration`, `step_duration`, `fps` and sequences). vizreel still takes chart timing from the YAML spec; CSV files in vizreel only carry a chart's data (bars, series, events), not its timing. vizreel rounds a clip to whole frames (`round(duration × fps)`), so vizsync gives times to the millisecond and leaves the rounding to vizreel.

### Where the charts come from

Either a chart map file (below), or the chart tags of the script (§1), or both. With tags, the paragraphs that carry the same chart id make one chart, in script order; `sequence` must be on every tag of a chart or on none, and a sequence needs 2 to 8 paragraphs. The tags of `examples/northwind-script.md` describe the same charts as `examples/chart-map.yaml`. The paragraphs of a chart must be consecutive, as for a map file. Problems in the tags are reported as `SCRIPT line N: charts.ID: message`. When both a map and a script are given, a chart that is in both is an error (`charts.ID is in both map.yaml and script.md; give each chart in one place`), and the charts of the map come first in the result. With neither charts nor tags the command stops with `No chart found`.

### Chart map

A vizreel spec is not a chart map: a spec lists its charts as a list (`charts:` followed by `- id: ...` items) and says how each chart looks, a chart map is a mapping from a chart id to the paragraphs it covers. A spec given as `--map` is recognised and reported as such (`this looks like a vizreel spec ... give a chart map ... or tag the paragraphs of the script`). Keep the chart map in a file of its own (for example `v01-chart-map.yaml`), or tag the script.

```yaml
version: 1
charts:
  peak-valuation:            # a single clip
    paragraphs: [P2]
  valuation:                 # one clip covering two paragraphs
    paragraphs: [P3, P4]
  collapse:                  # a vizreel sequence: one clip per paragraph, in order
    sequence: true
    paragraphs: [P6, P7, P8]
```

- `version` is required and must be `1`. `charts` must hold at least one chart.
- The key is the vizreel chart `id`: lowercase letters, digits and `-` only, and not a name Windows reserves (`con`, `prn`, `aux`, `nul`, `com1`–`com9`, `lpt1`–`lpt9`), as vizreel requires.
- `paragraphs` is required and lists one or more paragraph identifiers, each once. In `timing.json` they must exist, must not be `missing`, and must be consecutive and in script order.
- `sequence` is optional (`false` by default). With `sequence: true`, each paragraph is one clip of the sequence, in the order listed; vizreel allows 2 to 8 clips.
- Other fields are errors.
- All problems are reported together, each as `FILE: charts.ID: message`, and the command exits with code `1` without writing anything.

### Result

For the files `examples/chart-map.yaml` and `examples/timing.example.json`:

```yaml
charts:
  peak-valuation:
    start: 10.6
    duration: 10.5
  valuation:
    start: 21.9
    duration: 27.6
  collapse:
    start: 62.0
    duration: 14.1
    step_duration: 13.4
    clips:
      - { n: 1, start: 62.0, duration: 14.1 }
      - { n: 2, start: 76.1, duration: 13.4 }
      - { n: 3, start: 89.5, duration: 11.5 }
```

Charts are in the order of the chart map. Numbers have at least one decimal and at most three (milliseconds).

Single clip: `start` = start of the first paragraph (where to place the clip in the editor). `duration` = end of the last paragraph minus that start, plus `--pad` (default `0`).

Sequence: clips are cut back to back, so clip *k* runs from the start of paragraph *k* to the start of paragraph *k+1* (no gap on the timeline); the last clip runs to the end of its paragraph plus `--pad`. `start` and `duration` are the first clip's. vizreel has one `step_duration` for all later clips, so vizsync reports the longest later clip: a clip can be trimmed in the editor (it holds its last frame) but not made longer than it was rendered. The exact per-clip times are in `clips`.

The YAML goes to standard output, or to the file given with `-o` (then `Written: FILE` is printed). Warnings go to standard error. Values are in seconds and go into the vizreel spec's `duration:` / `step_duration:` fields.

Warnings (they do not change the exit code):

- A clip, or a clip of a sequence, shorter than 2 seconds (vizreel's minimum `duration`): `collapse: clip 2 is only 1.4 s long, vizreel needs at least 2 s.`
- A later clip of a sequence shorter than half of the reported `step_duration`: `collapse: clip 3 (4.0 s) is much shorter than step_duration (14.0 s); trim it in the editor.`
- A paragraph with status `low_confidence`: `collapse: P7 has low confidence (0.62), its time may be off.`

Exit codes: `0` success, `1` an unreadable or invalid `timing.json` or chart map, or an unwritable output file.

vizsync never edits a vizreel spec file itself, because rewriting YAML with a standard library drops the comments that scripts rely on for fact references.

## 7. Warnings

Each warning is a short sentence with the identifier. Examples: `P17: low confidence (0.62). The narration may differ from the script.`, `P23: not found in the audio.` (`parts` mode) or `P23: no audio file.` (`per-paragraph` mode), `notes.wav: matches no paragraph of the script, ignored.`, `P4: 730.8 s for 12 words, much longer than the other paragraphs. The script may be read more than once or out of order.` (`parts` mode: a found paragraph whose seconds per word exceed 3 times the median of all found paragraphs, at least 5 s long, needs 3 or more found paragraphs; its status stays `ok`), `chapters: only 2 chapters, YouTube needs at least 3.` Warnings are printed and stored in `timing.json`.

## 8. Errors

Expected failures print a message a user can act on and exit with code 1. Examples: `Script line 41: P9 has no blockquote (use --text inline?)`, `Audio file not found: part3.wav`. Messages name the file and line whenever possible.
