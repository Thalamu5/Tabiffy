# Tabiffy – notes for Claude

Read [SPEC.md](SPEC.md) first: it is the product brief. [README.md](README.md) lists what is built and
the deliberate deviations from the spec.

## Layout
- `backend/` – Python 3.11+, FastAPI. Package `tabiffy`. Pipeline stages in separate modules
  (`midi_import`, `mapping`, `quantize`, `chords`, `key_detect`, `solver/`, `audio/`). Canonical data model in `models.py`.
- `backend/tabiffy/audio/` – decode (ffmpeg) → transcribe (Basic Pitch ONNX; full mixes first go through librosa
  harmonic/percussive separation to drop drums) → beats (librosa) → `grid.BeatGrid` maps seconds to ticks
  (1 detected beat = 960 ticks). Each upload is ONE part. The user does instrument/stem separation (e.g. Demucs)
  themselves before uploading; don't add it to the app. Keep heavy imports lazy so the MIDI path works without them.
- `frontend/` – React + TypeScript + Vite + alphaTab (`@coderline/alphatab` 1.9). `src/lib/toAlphaTex.ts` converts
  TabiffyScore → alphaTex.
- `fixtures/` – self-made MIDI files (regenerate with `python scripts/make_fixtures.py`; copies live in
  `frontend/public/samples/`).

## Conventions
- TabiffyScore JSON is camelCase; Python uses snake_case with pydantic aliases. Serialize with `score.to_json()`.
- Guitar string 1 = highest string. Frets are relative to the capo. Fingers: 0 open, 1–4 index..pinky, "T" thumb.
- alphaTab differences: alphaTab's `Note.string` counts from the lowest string; alphaTex `{lf n}` is finger+1
  (1 = thumb, 2 = index…).
- Solver cost weights live in `backend/tabiffy/solver/weights.json`.
- Tuning presets (with string count, family and a "prior") are in `backend/tabiffy/tunings.py`; tuning suggestion
  scoring is in `backend/tabiffy/tuning_suggest.py` (tests with known-tuning riffs in `tests/test_tuning_suggest.py`).
  Uploads take `tuning` = "auto" or a preset key; the solver/fretboard/alphaTex handle any string count (4–8).
- Audio tests synthesize recordings (`backend/tests/audio_synth.py`); don't commit audio binaries
  other than `frontend/public/samples/demo_band.mp3` (regenerate with `python scripts/make_audio_sample.py`).
- Install Basic Pitch with `pip install --no-deps basic-pitch==0.4.0` (its declared deps pull TensorFlow).

## Checks (run before committing)
- `cd backend && ruff check . ../scripts && ruff format --check . ../scripts && pytest -q`
- `cd frontend && npm run lint && npm run typecheck && npm test && npm run build`
