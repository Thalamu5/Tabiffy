# Tabiffy

Upload a song file and get **guitar tab you can actually play**, with finger numbers,
an animated fretboard (or piano keyboard), playback, and exports to Guitar Pro, MIDI and PDF.

The full product brief is in [SPEC.md](SPEC.md).

## What works in v0.1

This version covers milestones **M0 (skeleton)** and **M1 (MIDI → tab)** from the spec, plus
early parts of M4 (visualizers) and M6 (transposition, capo suggestions, piano hands).

| Feature | Status |
|---|---|
| Upload a **MIDI** file (.mid/.midi), with live progress | ✅ |
| Upload **audio** (mp3/wav/…) | ⏳ Next milestone (M2). Shows a clear message for now. |
| Fret + string solver that finds a playable fingering (Viterbi over voicings and hand positions) | ✅ |
| Finger numbers 1–4, barre chords, stretches | ✅ |
| Chord names + chord diagrams above the staff | ✅ |
| Key, tempo and time-signature detection (taken from the MIDI, or estimated) | ✅ |
| Rhythm grid (1/8, 1/16, 1/16 + triplets, 1/32, off) | ✅ |
| Tab + standard notation, playback, speed 25–150 %, loop, metronome, count-in, mute/solo | ✅ |
| Animated **fretboard** with tuning, capo, finger numbers, barres, upcoming notes, left-handed mode | ✅ |
| Animated **piano** keyboard (colored by hand) | ✅ |
| Tunings: Standard, Drop D, D/Eb Standard, DADGAD, Open G/D/E, 7-string, 4/5-string bass, custom | ✅ |
| Capo 0–12, transpose ±12, "Suggest a capo" | ✅ |
| Play another instrument's part on guitar/bass/piano (octave mapping, too-dense chords reduced) | ✅ |
| Export **.gp** (Guitar Pro 7/8), **.mid**, **PDF** (print → "Save as PDF") | ✅ |
| Tab editor (click a note to change it, undo/redo) | ⏳ M5. The data model and solver already support locked (user-edited) notes. |

## Running it

### Option A: Docker (simplest)

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/), then in this folder run:

```bash
docker compose up --build
```

Open <http://localhost:8000>.

### Option B: for development

Needs **Python 3.11+** and **Node.js 20+**.

```bash
./scripts/dev.sh
```

Open <http://localhost:5173>. The first run installs everything; code changes reload automatically.

## Running the tests

```bash
cd backend && pytest          # solver, chords, quantizer, mapping, API, MIDI round trip
cd frontend && npm test       # score conversion + Guitar Pro round trip
```

GitHub Actions runs these, plus linting and type checks, on every push (`.github/workflows/ci.yml`).

## How it works

```
frontend/  React + TypeScript + Vite. alphaTab draws the score, plays it and writes .gp/.mid.
  src/lib/toAlphaTex.ts      TabiffyScore JSON → alphaTab's text format
  src/components/            ScoreView (player), Fretboard, Piano, SettingsPanel, Upload
backend/   Python + FastAPI
  tabiffy/midi_import.py     stage 1b: read MIDI
  tabiffy/mapping.py         stage 6: transpose / octave-shift into the instrument's range
  tabiffy/quantize.py        stage 8: snap to the rhythm grid
  tabiffy/chords.py          stage 5: chord names
  tabiffy/solver/            stage 7: fret/position solver + finger assignment
    weights.json             ← cost weights. Tune these to change fingering style.
  tabiffy/api.py             REST API (SPEC §8)
fixtures/  small self-made MIDI files used by tests and as in-app samples
```

The backend produces one canonical **TabiffyScore** JSON (SPEC §4); the frontend converts it
for alphaTab. Changing tuning/capo/instrument re-runs only the fast steps (about 0.3 s for 120 bars).

## Differences from the spec (deliberate, for v0.1)

- **No Redis/Postgres yet.** MIDI jobs finish in well under a second, so jobs run in a
  background thread and data is saved as files in `backend/data/`. The job runner and storage
  are small modules so they can be swapped for RQ/Celery + Postgres/S3 when audio arrives (M2/M3).
- **Quantize runs before the solver** (the spec lists it last), because the solver needs clean time slices.
- **No windowing in the solver.** The dynamic programming keeps the best 24 voicings per time
  slice, which keeps long songs fast without splitting them into windows.
- **PDF** uses alphaTab's print view (the spec's v1 approach); server-side PDFs are v1.1.
- **MIDI export** is done in the browser (alphaTab) and also available from the API (`/export?format=mid`).

## Known limitations

- Each MIDI track/channel becomes its own Tabiffy track. Merging tracks (e.g. piano left + right
  hand into one) is not in the UI yet.
- Chord names are a heuristic and can be wrong on busy arrangements.
- Notes that can't be placed comfortably are drawn red on the fretboard but not yet in the score.
- Original-audio sync mode needs audio input (M2).

## Next steps (from SPEC §9)

1. **M2 – Audio → notes:** Basic Pitch on solo recordings, beat/tempo detection, job queue with Redis.
2. **M3 – Full songs:** Demucs stem separation + MuScriptor (check its weights license first).
3. **M5 – Editor:** click-to-edit notes, keyboard entry, undo/redo, autosave, re-solve around locked notes.
