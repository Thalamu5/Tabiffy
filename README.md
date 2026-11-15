# Tabiffy

Upload a song (audio or MIDI) and get **guitar tab you can actually play**, with finger numbers,
an animated fretboard (or piano keyboard), playback, and exports to Guitar Pro, MIDI and PDF.

The full product brief is in [SPEC.md](SPEC.md).

## What works

v0.1 covered milestones **M0** (skeleton) and **M1** (MIDI → tab). v0.2 adds **M2** (audio → notes) and the
stem-separation part of **M3** (full songs).

| Feature | Status |
|---|---|
| Upload **audio** (mp3, wav, flac, ogg, m4a, up to 15 min) or **MIDI** | ✅ |
| **Full songs:** Demucs splits the mix into guitar, bass, piano, vocals, other (drums are ignored) | ✅ |
| **Solo recordings:** choose "solo guitar / bass / piano / other" to skip separation (faster, more accurate) | ✅ |
| Note detection with Spotify's **Basic Pitch** on each part | ✅ |
| Tempo, beats, bar lines and 3/4 vs 4/4 detection; key detection | ✅ |
| Fix the timing yourself: half/double tempo, shift bar lines, change time signature | ✅ |
| **Original-audio mode:** play your recording with the cursor following, or switch to the synth | ✅ |
| **Uncertain notes in red** + "Review next uncertain note" button | ✅ |
| Background job queue (Redis + worker) with progress per stage | ✅ |
| Fret + string solver with finger numbers 1–4, barres, stretches | ✅ |
| Chord names + diagrams, rhythm grid, capo/transpose/tunings, capo suggestions | ✅ |
| Tab + notation, playback (speed, loop, metronome, count-in, mute/solo) | ✅ |
| Animated **fretboard** and **piano** | ✅ |
| Export **.gp** (Guitar Pro 7/8), **.mid**, **PDF** | ✅ |
| Tab editor (click a note to fix it) | ⏳ M5 |
| MuScriptor (a stronger transcription model) | ⏳ Later in M3, once its weights license is checked |

### What to expect from full songs

Automatic transcription of full band recordings is still an unsolved problem. Expect the main riffs and
chords to come through and plenty of wrong or missing notes, especially in busy, distorted or heavily
produced songs. Clean, well-separated guitar parts work best. The red notes and the original-audio mode
are there to help you spot and judge the mistakes; the editor (M5) is how they'll get fixed.

**Processing time:** without a graphics card, separating a full song takes several minutes (it depends a
lot on the machine and hasn't been benchmarked yet); note detection adds under a minute for a typical song.
With an NVIDIA GPU, separation is much faster.

## Running it

### Option A: Docker (simplest)

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/), then in this folder run:

```bash
docker compose up --build
```

Open <http://localhost:8000>. The **first build takes a while** (it downloads PyTorch and the ~80 MB
Demucs model, a few GB in total); later starts are quick. This runs three services: the web app, a
background worker that processes uploads, and Redis (the queue between them).

### Option B: for development

Needs **Python 3.11+**, **Node.js 20+** and **ffmpeg** (for audio).

```bash
./scripts/dev.sh
```

Open <http://localhost:5173>. The first run installs everything (including PyTorch, so it takes a while);
code changes reload automatically. Here uploads are processed inside the backend; set `TABIFFY_REDIS_URL`
and run `rq worker tabiffy` to use a separate worker like Docker does.

## Running the tests

```bash
cd backend && pytest          # solver, chords, quantizer, mapping, API, MIDI round trip, audio pipeline
cd frontend && npm test       # score conversion + Guitar Pro round trip
```

GitHub Actions runs these, plus linting and type checks, on every push (`.github/workflows/ci.yml`).

## How it works

```
upload ─► decode (ffmpeg) ─► separate (Demucs) ─► notes per part (Basic Pitch) ─► beats/bars/key (librosa)
       └─ MIDI files skip straight to ───────────────────────────────────────────────► map to instrument range
                                                    ─► rhythm grid ─► fret/finger solver ─► TabiffyScore JSON
```

```
frontend/  React + TypeScript + Vite. alphaTab draws the score, plays it (synth or your recording) and writes .gp/.mid.
  src/lib/toAlphaTex.ts      TabiffyScore JSON → alphaTab's text format
  src/lib/alphaTabScore.ts   red uncertain notes, sync points to the original recording
  src/components/            ScoreView (player), Fretboard, Piano, SettingsPanel, TimingPanel, Upload
backend/   Python + FastAPI
  tabiffy/audio/             decode, separate (Demucs), transcribe (Basic Pitch), beats, grid, pipeline
  tabiffy/midi_import.py     MIDI input
  tabiffy/mapping.py         transpose / octave-shift into the instrument's range
  tabiffy/quantize.py        snap to the rhythm grid
  tabiffy/chords.py          chord names
  tabiffy/solver/            fret/position solver + finger assignment
    weights.json             ← cost weights. Tune these to change fingering style.
  tabiffy/jobs.py            background jobs (Redis/RQ, or a thread when Redis isn't configured)
  tabiffy/api.py             REST API (SPEC §8, plus /audio and /timing)
fixtures/  small self-made MIDI files used by tests and as in-app samples
```

Each detected beat becomes exactly one quarter note, so the tab lines up with the band even if the tempo
drifts; the score gets one steady tempo, and per-beat **sync points** keep the cursor on the original
recording. Changing tuning/capo/instrument re-runs only the fast steps (about 0.3 s for 120 bars); changing
the timing re-uses the stored notes, so nothing is transcribed twice.

## Differences from the spec (deliberate)

- **Beat tracking uses librosa** rather than madmom (unmaintained, doesn't install on current Python) or
  beat_this (better, but needs a model download; a good upgrade later). Bar lines are a heuristic
  (low-end energy + where the harmony changes), which is why the "shift bar lines" button exists.
- **Key comes from the transcribed notes** (Krumhansl-Schmuckler), not essentia.
- **Basic Pitch runs its ONNX model** (no TensorFlow), installed with `--no-deps` (see `backend/pyproject.toml`).
- **"Confidence" is a heuristic** from Basic Pitch's note strength and length, not a calibrated probability.
- **No Postgres yet.** Scores are JSON files in the data folder; Redis is used for the job queue only.
  Large WAV intermediates (stems) are deleted after processing; the notes, beats and an MP3 are kept.
- **Quantize runs before the solver**, and the solver keeps the best 24 voicings per slice instead of windowing.
- **PDF** uses alphaTab's print view; server-side PDFs are v1.1.

## Known limitations

- Techniques (bends, slides, hammer-ons, vibrato) aren't detected from audio yet.
- Vocals become a single melody line; drums are ignored (non-goal).
- Each part (or MIDI track) is its own track; merging tracks isn't in the UI yet.
- Chord names are a heuristic and can be wrong on busy arrangements.
- Time signatures for audio are x/4 only (no 6/8 yet).

## Next steps (from SPEC §9)

1. **UI/UX pass** based on testing with real songs.
2. **M5 – Editor:** click-to-edit notes, keyboard entry, undo/redo, autosave, re-solve around locked notes.
3. **M3 (rest):** MuScriptor as an alternative transcriber once its weights license is confirmed; pick which parts to keep.
4. Accuracy tracking: `mir_eval` note F1 on GuitarSet / MAESTRO samples as a nightly job.
