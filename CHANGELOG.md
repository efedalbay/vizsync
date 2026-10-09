# Changelog

All notable changes to vizsync are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [0.1.0] - Unreleased

The first release. Given a narration recording and the numbered script it was read from, vizsync
reports where each script paragraph starts and ends in the audio, and writes the files a video
maker needs from that.

### Added

- `vizsync check SCRIPT`: parses a script and reports every problem with its line. A script is a Markdown file with numbered paragraphs (`P1 — ...`, also `**P1** —`, `*P1* —` and `__P1__ —`), chapters from headings, and either the paragraph line or the blockquote under it as the text to align (`--text inline` or `quote`, for bilingual scripts).
- `vizsync align AUDIO... --script SCRIPT`: finds every paragraph in the audio with a local speech model (faster-whisper, CPU or NVIDIA GPU, no account, no upload). The script is known, so a misheard word does not lose a paragraph: words are matched with an alignment that tolerates recognition errors, and a paragraph that is not found is reported as `missing` instead of being given invented times.
  - The audio can be one file, several parts in order, or one file per paragraph. Files, folders and wildcards are expanded by vizsync itself, so they work in PowerShell.
  - Exit codes: `0` success, `1` a user error or, with `--strict`, any warning, `2` a paragraph was not found.
  - A paragraph that spans much longer than its words suggest (a script read twice, or out of order) gets a warning.
- Output files: `timing.json` (the source of truth), `timing.csv`, `chapters.txt` (YouTube rules and their warnings), `markers.edl` (one marker per paragraph, `--fps` and `--timeline-start`), and `captions.srt` (the script text as subtitles, at most two lines of 42 characters, timed by the spoken words).
- `--join`, for one audio file per paragraph (WAV, or MP3 as ElevenLabs gives): joins the files into `narration.wav` with a silence between paragraphs and a longer one between chapters (`--paragraph-gap`, `--chapter-gap`), and gives the times of that file to the sample. Samples are copied unchanged, an MP3 is decoded once to 16-bit PCM, and files of different sample rates or channel counts stop the run. `--trim` first cuts the silence at the start and end of every file.
- `<!-- pause: 4.0 -->` under a paragraph sets the silence after it to that many seconds when joining (`--join`), instead of the paragraph or chapter gap, for example where an intro is added later. Every output file includes it.
- `vizsync durations TIMING_JSON`: when each chart clip of a [vizreel](https://github.com/efedalbay/vizreel) video goes on the timeline and how long it must be (`start`, `duration`, and `step_duration` and `clips` for a sequence). The charts come from a chart map file, from `<!-- chart: ID -->` tags under the paragraphs of the script, or both.
- A number spelled out in the script, such as "three hundred and seventy-five million", is read as 375 million, the way speech recognition writes it, so a short paragraph made of a spoken amount is no longer reported as `missing`. Years read as "twenty twenty-three" are not covered.
- Text output is written as UTF-8 whenever it is not a terminal, so paths and titles with Turkish letters survive redirection and capture.

### Notes

- On a laptop CPU (Intel Core i5-12500H, no GPU) the default `small.en` model recognized 13 minutes 25 seconds of audio in 2 minutes 29 seconds.
- `markers.edl` follows the file DaVinci Resolve writes for timeline markers, but has not been tried in Resolve yet.
- PyAV is limited to versions below 19 because faster-whisper 1.2 opens audio with an argument PyAV 19 removed.
- `--device auto` uses an NVIDIA GPU only when its cuBLAS 12 and cuDNN 9 libraries can be loaded; otherwise the CPU.
