# Test fixture: the Northwind clip

`northwind.wav` is the recording the slow tests (`uv run pytest -m slow -rs`) and
`scripts/check-steps.ps1` use. It is in the repository (38 s, 16 kHz mono).

## What it must be

- Someone reading the English lines of `examples/northwind-script.md`, in order, P1 to P8.
- **Your own voice, or a synthetic voice you generated yourself.** Never a recording of anyone
  else, and nothing you do not have the right to publish: the repository is MIT-licensed and
  this file is committed to it.
- A plain PCM WAV (16-bit). About 40 seconds. Mono is fine; 16 kHz is enough.
- **A pause of at least one second between paragraphs**, and no pause inside a paragraph longer
  than half a second. The split tests cut the clip in those pauses.
- Read the numbers the natural way ("seven hundred forty million", "twenty sixteen").

## The lines to read

1. Northwind was worth 740 million dollars at its peak.
2. Then one decision changed everything.
3. The company started in 2016 with a small team.
4. Within two years its value grew twentyfold.
5. Everyone believed the growth would continue.
6. Then its biggest customer did not renew the contract.
7. One third of its revenue disappeared overnight.
8. Eighteen months later, Northwind filed for bankruptcy.

## Making the WAV

Record with any tool (for example Windows Sound Recorder, which saves `.m4a`), then convert:

```powershell
uv run python scripts/to-wav.py C:\path\to\recording.m4a tests\fixtures\northwind.wav
```

## Checking it

```powershell
uv run vizsync align tests\fixtures\northwind.wav --script examples\northwind-script.md --out out\fixture
```

All eight paragraphs should be `ok`. The first run downloads the speech model.
