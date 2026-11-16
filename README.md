# Tabiffy

Upload a song (audio or MIDI) and get **guitar tab you can actually play**, with finger numbers,
an animated fretboard (or piano keyboard), playback, and exports to Guitar Pro, MIDI and PDF.

The full product brief is in [SPEC.md](SPEC.md).

## What works

v0.1 covered milestones **M0** (skeleton) and **M1** (MIDI → tab). v0.2 adds **M2** (audio → notes), tuning
detection, slides / hammer-ons / pull-offs, two-hand tapping, triplet rhythms and a key & scale explainer.
Tabiffy does **not** separate instruments itself: to tab one instrument from a band recording, split it out
first with a stem-separation tool of your choice and upload that part.

| Feature | Status |
|---|---|
| Upload **audio** (mp3, wav, flac, ogg, m4a, up to 15 min) or **MIDI** | ✅ |
| Say what's in the file (guitar, bass, piano, vocals, other, or a full band mix) to tune note detection | ✅ |
| **Tuning detection:** suggests the best-fitting guitar tuning (6, 7 or 8 strings) with reasons and alternatives | ✅ |
| Or pick the tuning at upload / any time, and the tab sticks to it | ✅ |
| 6-string (Standard, Eb/D/C/B Standard, Drop D/C#/C/B/A, DADGAD, Open G/D/E), 7-string (B/A Standard, Drop A/G), 8-string (F# Standard, Drop E), custom | ✅ |
| **Slides, hammer-ons, pull-offs** found in the audio; ones we only suspect are shown in blue | ✅ (suggestions) |
| **Two-hand tapping**: tick it at upload (or in Track settings) and wide jumps on one string are written as taps ("T") | ✅ |
| Triplet rhythms, including 16th-note triplets (six notes per beat) | ✅ |
| **Key & scale**: click the key to see the scale (modes, harmonic/melodic minor, pentatonic, blues…), why, and the scale on the fretboard | ✅ |
| Full band mixes are transcribed as one part, with drum hits filtered out first | ✅ (rough) |
| Note detection with Spotify's **Basic Pitch** on each part | ✅ |
| Tempo, beats, bar lines and 3/4 vs 4/4 detection; key detection | ✅ |
| Fix the timing yourself: half/double tempo, shift bar lines, change time signature | ✅ |
| **Original-audio mode:** play your recording with the cursor following, or switch to the synth | ✅ |
| **Uncertain notes in red** + "Review next uncertain note" button | ✅ |
| Background job queue (Redis + worker) with progress per stage | ✅ |
| Fret + string solver with finger numbers 1–4, barres, stretches | ✅ |
| Chord names + chord boxes (placed at the right fret), rhythm grid, capo/transpose, capo suggestions | ✅ |
| Tab + notation, playback (speed, loop, metronome, count-in, mute/solo) | ✅ |
| Animated **fretboard** and **piano** | ✅ |
| Export **.gp** (Guitar Pro 7/8), **.mid**, **PDF** | ✅ |
| Tab editor (click a note to fix it) | ⏳ M5 |
| MuScriptor (a stronger transcription model) | ⏳ Later, once its weights license is checked |

### What to expect

Automatic transcription is far from perfect. A clean recording of one instrument (or a well-separated
part) gives the best results; a full band mix gives rough results, since instruments mask each other.
Slides, hammer-ons and pull-offs are detected from how each note starts (a pick attack or not) and whether
the pitch glides; most are shown as blue suggestions, since distortion and mixing blur these clues. Bends and
vibrato aren't detected yet. Tapping isn't guessed automatically: tell the app at upload. The red and blue notes
and the original-audio mode are there to help you judge the tab; the editor (M5) is how mistakes will get fixed.

**Processing time:** in testing on a 4-core machine, a 4-minute recording took about 13 seconds as a
single instrument and about 22 seconds as a full mix (no graphics card needed).

## Running it

### Option A: Docker (simplest)

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/), then in this folder run:

```bash
docker compose up --build
```

Open <http://localhost:8000>. The first build takes a few minutes; later starts are quick. This runs three
services: the web app, a background worker that processes uploads, and Redis (the queue between them).
By default it is only reachable from your own computer (see the comment in `docker-compose.yml` to change that).

### Option B: for development

Needs **Python 3.11+**, **Node.js 20+** and **ffmpeg** (for audio).

```bash
./scripts/dev.sh
```

Open <http://localhost:5173>. The first run installs everything; code changes reload automatically. Here uploads are processed inside the backend; set `TABIFFY_REDIS_URL`
and run `rq worker tabiffy` to use a separate worker like Docker does.

## Running the tests

```bash
cd backend && pytest          # solver, chords, scales, techniques, tapping, API, security, audio pipeline
cd frontend && npm test       # score conversion + Guitar Pro round trip
```

GitHub Actions runs these, plus linting and type checks, on every push (`.github/workflows/ci.yml`).

## How it works

```
upload ─► decode (ffmpeg) ─► [full mix: filter out drums] ─► notes (Basic Pitch) ─► beats/bars/key (librosa)
       └─ MIDI files skip straight to ───────────────────────────────────────────────► map to instrument range
                                                    ─► rhythm grid ─► fret/finger solver ─► TabiffyScore JSON
```

```
frontend/  React + TypeScript + Vite. alphaTab draws the score, plays it (synth or your recording) and writes .gp/.mid.
  src/lib/toAlphaTex.ts      TabiffyScore JSON → alphaTab's text format
  src/lib/alphaTabScore.ts   red uncertain notes, sync points to the original recording
  src/components/            ScoreView (player), Fretboard, Piano, SettingsPanel, TimingPanel, Upload
backend/   Python + FastAPI
  tabiffy/audio/             decode, transcribe (Basic Pitch), beats, grid, pipeline
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

### How techniques and tapping are found

Each note gets two clues from the audio: how strong its pick attack is (a burst of high-frequency noise) and
whether its pitch glided in from the previous note. Notes in a single-note line that follow each other with no
attack become hammer-ons/pull-offs, or slides when the pitch glides; the fret solver then keeps each pair on one
string. With tapping on, ringing notes are cut into one line, quiet octave "ghosts" (string overtones) are
dropped, and the solver may tap a note that the fretting hand can't reach, writing tap-pull-hammer runs like
16-1-4 on one string.

### How the key and scale are found

The home note (tonic) comes from what's played most, the bass notes, phrase endings and chord roots. Every
scale on that root is then scored by how many played notes fit it, so A minor and C major (same notes) are told
apart by which note feels like home. The window lists the reasons and the runner-ups.

### How tuning detection works

Every guitar tuning preset is tried on the detected notes with the real fret solver, and scored on:
notes it can't reach (below its lowest string), how awkward the resulting tab is (stretches, big jumps;
open strings count in its favour, which is how drop-tuned riffs give themselves away), low strings that
nothing needs (so it doesn't suggest an 8-string when a 7 will do), and a small preference for common
tunings. The lowest ~3% of notes are treated as possible detection errors (octave mistakes, bass bleed).

It's an educated guess: two tunings often fit the same notes (e.g. Drop C vs 7-string B), so the app
shows its top three with a reason for each. Detection is most reliable on a guitar-only recording; on a
full band mix, bass notes can pull it toward lower tunings. Weights are in `backend/tabiffy/tuning_suggest.py`.

## Differences from the spec (deliberate)

- **Beat tracking uses librosa** rather than madmom (unmaintained, doesn't install on current Python) or
  beat_this (better, but needs a model download; a good upgrade later). Bar lines are a heuristic
  (low-end energy + where the harmony changes), which is why the "shift bar lines" button exists.
- **Key comes from the transcribed notes** (Krumhansl-Schmuckler), not essentia.
- **Basic Pitch runs its ONNX model** (no TensorFlow), installed with `--no-deps` (see `backend/pyproject.toml`).
- **"Confidence" is a heuristic** from Basic Pitch's note strength and length, not a calibrated probability.
- **No Postgres yet.** Scores are JSON files in the data folder; Redis is used for the job queue only.
  The large decoded WAV is deleted after processing; the notes, beats and an MP3 are kept.
- **Quantize runs before the solver**, and the solver keeps the best 24 voicings per slice instead of windowing.
- **PDF** uses alphaTab's print view; server-side PDFs are v1.1.

## Known limitations

- Techniques (bends, slides, hammer-ons, vibrato) aren't detected from audio yet.
- Vocals become a single melody line; drums aren't transcribed (non-goal).
- One audio file = one part. Combining several separately uploaded parts into one score isn't supported yet.
- Each MIDI track is its own track; merging tracks isn't in the UI yet.
- Chord names are a heuristic and can be wrong on busy arrangements.
- Time signatures for audio are x/4 only (no 6/8 yet).
- Tuning detection can't tell tunings apart when the notes fit both equally; more bass tunings come with the bass work.
- Chord boxes show alphaTab's relative fret numbers above each box; finger numbers inside the dots aren't possible yet.
- If a straight song shows stray triplets, set **Rhythm grid** to "1/16 notes".

## Security

- Uploads: size-limited (200 MB, 15 minutes), checked by extension, and decoded by ffmpeg restricted to audio
  formats and the uploaded file only (no playlists, no network). Other requests are limited to 20 MB.
- Errors shown in the app are generic; details go to the server log only.
- The Docker container runs as an unprivileged user; Redis is not exposed outside Docker.
- No accounts or passwords exist yet. Don't put the app on the public internet without adding sign-in and
  rate limiting. Never commit secrets: `.env` files are git-ignored.

## Next steps (from SPEC §9)

1. **UI/UX pass** based on testing with real songs.
2. **M5 – Editor:** click-to-edit notes, keyboard entry, undo/redo, autosave, re-solve around locked notes.
3. Using the low strings of a 7/8-string when re-calculating (parked for now).
4. MuScriptor as an alternative transcriber once its weights license is confirmed.
5. Accuracy tracking: `mir_eval` note F1 on GuitarSet / MAESTRO samples as a nightly job.
