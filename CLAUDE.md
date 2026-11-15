# Tabiffy – notes for Claude

Read [SPEC.md](SPEC.md) first: it is the product brief. [README.md](README.md) lists what is built and
the deliberate deviations from the spec.

## Layout
- `backend/` – Python 3.11+, FastAPI. Package `tabiffy`. Pipeline stages in separate modules
  (`midi_import`, `mapping`, `quantize`, `chords`, `key_detect`, `solver/`). Canonical data model in `models.py`.
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

## Checks (run before committing)
- `cd backend && ruff check . ../scripts && ruff format --check . ../scripts && pytest -q`
- `cd frontend && npm run lint && npm run typecheck && npm test && npm run build`
