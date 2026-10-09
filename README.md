# vizsync

Find out where each paragraph of your script starts and ends in your narration audio.

vizsync takes a narration recording and the numbered script it was read from, and returns the start and end time of every paragraph. It is built for video makers who write a script first, record a voice-over, and then need to know exactly when to place charts, cut footage or add chapter markers.

> **Status: first release (0.1.0).** `vizsync check` and `vizsync align` (with `timing.json`, `timing.csv`, `chapters.txt`, `markers.edl` and `captions.srt`) work, and so does `vizsync durations` (chart timing for vizreel). The DaVinci Resolve import of `markers.edl` has not been tried in Resolve yet.

## Why

Speech-to-text tools answer "what was said?". vizsync answers a different question: "I already know what was said, **where** is each paragraph?"

Because the script is known, vizsync does not need a perfect transcript. Speech recognition may mishear a name, but the order and the surrounding words still pin every paragraph to the right place in the audio.

## What you get

```
$ vizsync align narration.wav --script northwind.md -o out/

P1     00:00.0 ->  00:03.6     3.5 s  ok
P2     00:05.7 ->  00:07.5     1.8 s  ok
P3     00:09.7 ->  00:13.0     3.3 s  ok
P4     00:15.2 ->  00:17.4     2.3 s  ok
P5     00:19.6 ->  00:21.6     1.9 s  ok
P6     00:23.7 ->  00:26.4     2.7 s  ok
P7     00:28.7 ->  00:30.9     2.2 s  ok
P8     00:33.0 ->  00:36.1     3.1 s  ok
8 ok, 0 low confidence, 0 missing
```

(The output of the Northwind example in this repository: `examples/northwind-script.md` and the 38-second clip `tests/fixtures/northwind.wav`.)

Written to `out/`:

| File | Use |
|---|---|
| `timing.json` | Full result. The source of truth for other tools |
| `timing.csv` | Open in a spreadsheet |
| `chapters.txt` | Paste into a YouTube description |
| `markers.edl` | Import as timeline markers in DaVinci Resolve |
| `captions.srt` | Subtitles with the exact script text, for YouTube or an editor |

With a small map file, vizsync also works out when each chart clip goes on the timeline and how long it must be, for use with [vizreel](https://github.com/efedalbay/vizreel) (see below).

## Script format

Paragraphs are numbered. Headings become chapters. The text to align is either the line itself or the blockquote under it (useful for bilingual scripts). Full rules in [SPEC.md](https://github.com/efedalbay/vizsync/blob/main/docs/SPEC.md).

```markdown
## 1. The Hook

P1 — Northwind was worth 740 million dollars at its peak.

P2 — Then one decision changed everything.
```

## Using the results

**YouTube chapters.** Open `chapters.txt`, copy the lines into the video description. YouTube needs the first chapter at `00:00`, at least three chapters and at least 10 seconds per chapter; vizsync warns when the list breaks one of these.

**DaVinci Resolve.** Run `vizsync align` with the frame rate of your timeline, for example `--fps 25`. In Resolve choose Timeline → Import → Timeline Markers from EDL and pick `markers.edl`. Resolve starts new timelines at `01:00:00:00`, which is what vizsync assumes; if your timeline starts at `00:00:00:00`, add `--timeline-start 00:00:00:00`.

**Subtitles.** `captions.srt` holds the text of your script, at most two lines of 42 characters per cue, timed by the spoken words, so it needs no correction for misheard names. Upload it to YouTube (Subtitles → Add language → Upload file → With timing) or import it in your editor. When the narration is one file per paragraph, cue times inside a paragraph are spread by text length, since nothing was recognized.

**CapCut.** CapCut cannot import markers from a file (none is known to vizsync). Open `timing.csv` in a spreadsheet, or `chapters.txt`, and place your cuts, text or charts at those times by hand.

## Chart timing for vizreel

The full flow, from script to vizreel spec:

1. Write the script and check it: `vizsync check northwind.md`.
2. Record the narration and align it: `vizsync align narration.wav --script northwind.md -o out`.
3. Say which paragraphs each chart covers. Either write a chart map ([`examples/chart-map.yaml`](https://github.com/efedalbay/vizsync/blob/main/examples/chart-map.yaml)), or tag the paragraphs in the script itself with a comment below each paragraph, `<!-- chart: valuation -->` (and `<!-- chart: collapse, sequence -->` on every paragraph of a sequence), as [`examples/northwind-script.md`](https://github.com/efedalbay/vizsync/blob/main/examples/northwind-script.md) does. Both can be used together. The chart map is a file of its own, not the vizreel spec (a spec lists its charts as a list and vizsync says so if you give it as the map). The chart map:

   ```yaml
   version: 1
   charts:
     peak-valuation:        # the vizreel chart id; one clip
       paragraphs: [P2]
     valuation:             # one clip over two paragraphs
       paragraphs: [P3, P4]
     collapse:              # a vizreel sequence: one clip per paragraph
       sequence: true
       paragraphs: [P6, P7, P8]
   ```

4. Work out the timing: `vizsync durations out/timing.json --map chart-map.yaml` or `vizsync durations out/timing.json --script northwind.md` (add `-o chart-timing.yaml` to write a file, `--pad 0.5` to give every clip half a second more at the end). For the example files in `examples/` it prints:

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

5. Copy `duration` (and `step_duration` for a sequence) into the chart's entry in your vizreel spec, render with vizreel, and place each clip in your editor at its `start`. The clips of a sequence play back to back from the first `start`. vizsync never edits your spec, so the comments in it stay.

A clip can be trimmed in the editor but not made longer than it was rendered, which is why a sequence reports the longest later clip as `step_duration`; the exact length of every clip is in `clips`.

## Audio input

Give vizsync whatever you have:

- one long file for the whole video
- several parts in order (for example 1–2 minute takes)
- one file per paragraph (`P08.wav`)

The output is the same in every case, except that with one file per paragraph the silence between the files is gone, so absolute times are not known. Add `--join` to get them: vizsync joins the files into `narration.wav` with silence between them and gives the times of that file.

```
vizsync align P*.wav --script script.md -o out --join --paragraph-gap 0.6 --chapter-gap 1.2
```

The samples of WAV files are copied unchanged (nothing is encoded again). MP3 files, which some text-to-speech services give (ElevenLabs, for example), are decoded once to 16-bit PCM and joined the same way; the MP3 files themselves are left as they are. All files must have the same sample rate, channel count and sample size, so a WAV joined with MP3 files must be 16-bit. vizsync never converts a sample rate or a channel count.

To leave room for something added later, such as an intro, put `<!-- pause: 4.0 -->` under a paragraph: the silence after it is then 4.0 seconds instead of the normal gap, and every time and output file includes it.

## Installation

Python 3.11 or newer. Install it from PyPI with any of:

```
pip install vizsync
uv tool install vizsync
pipx install vizsync
```

Then:

```
vizsync --version
vizsync check script.md
vizsync align narration.wav --script script.md --out out
```

To work on vizsync itself, or to run the examples of this repository, use a clone with [uv](https://docs.astral.sh/uv/):

```
uv sync
uv run vizsync check examples/northwind-script.md
uv run vizsync align narration.wav --script examples/northwind-script.md --out out
```

Speech recognition runs locally on your computer with [faster-whisper](https://github.com/SYSTRAN/faster-whisper). The first run downloads the speech model (about 480 MB for the default `small.en`; use `--model tiny.en` for a quick, less accurate run). No account, no upload, no cost per use.

**Speed.** On a laptop CPU (Intel Core i5-12500H, 16 GB RAM, no GPU in use) the default `small.en` model recognized 13 minutes 25 seconds of audio in 2 minutes 29 seconds, about 5 times faster than real time. Matching the script takes well under a second. Measured with `.\scripts\check-local.ps1 -Speed` on the Northwind clip repeated to 13 minutes, since recognition time depends on the length of the audio, not on what is said.

## Documents

- [SPEC.md](https://github.com/efedalbay/vizsync/blob/main/docs/SPEC.md): script format, commands, output files
- [ARCHITECTURE.md](https://github.com/efedalbay/vizsync/blob/main/docs/ARCHITECTURE.md): how it works and why
- [ROADMAP.md](https://github.com/efedalbay/vizsync/blob/main/docs/ROADMAP.md): milestones
- [CHANGELOG.md](https://github.com/efedalbay/vizsync/blob/main/CHANGELOG.md): what changed in each version

## License

MIT
