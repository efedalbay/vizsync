# vizsync

Find out where each paragraph of your script starts and ends in your narration audio.

vizsync takes a narration recording and the numbered script it was read from, and returns the start and end time of every paragraph. It is built for video makers who write a script first, record a voice-over, and then need to know exactly when to place charts, cut footage or add chapter markers.

> **Status: in development, not released.** `vizsync check` and `vizsync align` (with `timing.json`, `timing.csv`, `chapters.txt` and `markers.edl`) work from source. `vizsync durations` (chart timing for vizreel) works too. The DaVinci Resolve import of `markers.edl` has not been tried in Resolve yet, and the package is not on PyPI yet.

## Why

Speech-to-text tools answer "what was said?". vizsync answers a different question: "I already know what was said, **where** is each paragraph?"

Because the script is known, vizsync does not need a perfect transcript. Speech recognition may mishear a name, but the order and the surrounding words still pin every paragraph to the right place in the audio.

## What you get

```
$ vizsync align narration.wav --script northwind.md -o out/

P1     00:00.4 ->  00:09.8     9.4 s  ok
P2     00:10.6 ->  00:21.1    10.5 s  ok
P3     00:21.9 ->  00:38.0    16.1 s  ok
```

Written to `out/`:

| File | Use |
|---|---|
| `timing.json` | Full result. The source of truth for other tools |
| `timing.csv` | Open in a spreadsheet |
| `chapters.txt` | Paste into a YouTube description |
| `markers.edl` | Import as timeline markers in DaVinci Resolve |

With a small map file, vizsync also works out when each chart clip goes on the timeline and how long it must be, for use with [vizreel](https://github.com/efedalbay/vizreel) (see below).

## Script format

Paragraphs are numbered. Headings become chapters. The text to align is either the line itself or the blockquote under it (useful for bilingual scripts). Full rules in `docs/SPEC.md`.

```markdown
## 1. The Hook

P1 — Northwind was worth 740 million dollars at its peak.

P2 — Then one decision changed everything.
```

## Using the results

**YouTube chapters.** Open `chapters.txt`, copy the lines into the video description. YouTube needs the first chapter at `00:00`, at least three chapters and at least 10 seconds per chapter; vizsync warns when the list breaks one of these.

**DaVinci Resolve.** Run `vizsync align` with the frame rate of your timeline, for example `--fps 25`. In Resolve choose Timeline → Import → Timeline Markers from EDL and pick `markers.edl`. Resolve starts new timelines at `01:00:00:00`, which is what vizsync assumes; if your timeline starts at `00:00:00:00`, add `--timeline-start 00:00:00:00`.

**CapCut.** CapCut cannot import markers from a file (none is known to vizsync). Open `timing.csv` in a spreadsheet, or `chapters.txt`, and place your cuts, text or charts at those times by hand.

## Chart timing for vizreel

The full flow, from script to vizreel spec:

1. Write the script and check it: `vizsync check northwind.md`.
2. Record the narration and align it: `vizsync align narration.wav --script northwind.md -o out`.
3. Say which paragraphs each chart covers, in a chart map (`examples/chart-map.yaml`):

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

4. Work out the timing: `vizsync durations out/timing.json --map chart-map.yaml` (add `-o chart-timing.yaml` to write a file, `--pad 0.5` to give every clip half a second more at the end). For the example files in `examples/` it prints:

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

The samples are copied unchanged (nothing is encoded again), so the files must be plain PCM WAV with the same sample rate, channels and sample size. `--trim` first cuts the silence at the start and end of each file, so equal gaps sound equal.

## Installation

Not on PyPI yet. From a clone of this repository, with [uv](https://docs.astral.sh/uv/):

```
uv sync
uv run vizsync check examples/northwind-script.md
uv run vizsync align narration.wav --script examples/northwind-script.md --out out
```

Python 3.11+. Speech recognition runs locally on your computer with [faster-whisper](https://github.com/SYSTRAN/faster-whisper). The first run downloads the speech model (about 480 MB for the default `small.en`; use `--model tiny.en` for a quick, less accurate run). No account, no upload, no cost per use.

**Speed.** On a laptop CPU (Intel Core i5-12500H, 16 GB RAM, no GPU in use) the default `small.en` model recognized 13 minutes 25 seconds of audio in 2 minutes 29 seconds, about 5 times faster than real time. Matching the script takes well under a second. Measured with `.\scripts\check-local.ps1 -Speed` on the Northwind clip repeated to 13 minutes, since recognition time depends on the length of the audio, not on what is said.

When it is released: `pip install vizsync`.

## Documents

- `docs/SPEC.md` — script format, commands, output files
- `docs/ARCHITECTURE.md` — how it works and why
- `docs/ROADMAP.md` — milestones

## License

MIT
