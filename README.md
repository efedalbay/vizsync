# vizsync

Find out where each paragraph of your script starts and ends in your narration audio.

vizsync takes a narration recording and the numbered script it was read from, and returns the start and end time of every paragraph. It is built for video makers who write a script first, record a voice-over, and then need to know exactly when to place charts, cut footage or add chapter markers.

> **Status: planning.** The design is written (see `docs/`), the code is not. Nothing here is installable yet.

## Why

Speech-to-text tools answer "what was said?". vizsync answers a different question: "I already know what was said, **where** is each paragraph?"

Because the script is known, vizsync does not need a perfect transcript. Speech recognition may mishear a name, but the order and the surrounding words still pin every paragraph to the right place in the audio.

## What you get

```
$ vizsync align narration.wav --script northwind.md -o out/

P1    00:00.4 → 00:09.8    9.4 s   ok
P2    00:10.6 → 00:21.1   10.5 s   ok
P3    00:21.9 → 00:38.0   16.1 s   ok
```

Written to `out/`:

| File | Use |
|---|---|
| `timing.json` | Full result. The source of truth for other tools |
| `timing.csv` | Open in a spreadsheet |
| `chapters.txt` | Paste into a YouTube description |
| `markers.edl` | Import as timeline markers in DaVinci Resolve |

With a small map file, vizsync also works out how long each chart clip must be, for use with [vizreel](https://github.com/efedalbay/vizreel).

## Script format

Paragraphs are numbered. Headings become chapters. The text to align is either the line itself or the blockquote under it (useful for bilingual scripts). Full rules in `docs/SPEC.md`.

```markdown
## 1. The Hook

P1 — Northwind was worth 740 million dollars at its peak.

P2 — Then one decision changed everything.
```

## Audio input

Give vizsync whatever you have:

- one long file for the whole video
- several parts in order (for example 1–2 minute takes)
- one file per paragraph (`P08.wav`)

The output is the same in every case.

## Planned installation

```
pip install vizsync
```

Python 3.11+. Speech recognition runs locally on your computer with [faster-whisper](https://github.com/SYSTRAN/faster-whisper). No account, no upload, no cost per use.

## Documents

- `docs/SPEC.md` — script format, commands, output files
- `docs/ARCHITECTURE.md` — how it works and why
- `docs/ROADMAP.md` — milestones

## License

MIT
