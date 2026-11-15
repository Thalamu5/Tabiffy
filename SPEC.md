# Tabiffy: Product & Technical Spec (v0.1)

> Hand this file to Claude Code as the starting brief. Put it in the repo root (for example as `SPEC.md`) and reference it from `CLAUDE.md`.

## 1. What we're building

A web app where a user uploads an audio or MIDI file. The app:

1. Finds the notes and chords being played.
2. Writes **guitar tablature** for them, with a fingering a person can actually play and finger numbers (1 = index, 2 = middle, 3 = ring, 4 = pinky).
3. Can also show the same music on a **piano**, showing which keys to press and how to play them.
4. Handles music that has no guitar or piano by moving it into the target instrument's playable range (transposing).
5. Plays the result back inside the app with an animated fretboard/keyboard, the current tuning and finger numbers.
6. Lets the user **edit** the tablature, because automatic transcription will make mistakes.
7. Exports to **PDF**, **MIDI** and **Guitar Pro (.gp, GP7/8)**.

### Non-goals for v1
- Real-time/live microphone transcription.
- Vocals-to-melody as a separate product (we may still transcribe the vocal line as a note line to turn into tab).
- Drums notation.
- Native mobile apps (the web app should be responsive).

## 2. Architecture

```
┌──────────────────────────── Frontend (TypeScript, React + Vite) ───────────────────────────┐
│ Upload UI → Job status → Score view (alphaTab) ↔ Tab editor → Player + Fretboard/Piano viz │
│ Exports: .gp & .mid (alphaTab exporters, client-side), PDF (server or print stylesheet)    │
└───────────────▲────────────────────────────────────────────────────────────────────────────┘
                │ REST + job polling / SSE
┌───────────────┴──────────── Backend (Python 3.11+, FastAPI) ───────────────────────────────┐
│ /upload → job queue (RQ or Celery + Redis) → Pipeline worker (GPU optional)                │
│   1. Decode/normalize   2. Stem separation   3. Transcription   4. Beat/tempo/key          │
│   5. Chord labeling     6. Instrument mapping/transpose   7. Fret + finger solver          │
│   → TabiffyScore JSON (canonical) stored in Postgres/S3-compatible storage                 │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Canonical data format:** the backend produces a `TabiffyScore` JSON (§4). The frontend turns it into an alphaTab `Score` for drawing, playback and Guitar Pro/MIDI export. Edits are saved back as `TabiffyScore`.

## 3. Pipeline stages (backend)

| # | Stage | Primary tool | Fallback / notes |
|---|-------|--------------|------------------|
| 1 | Decode & normalize (mp3/wav/flac/ogg/m4a → 44.1 kHz WAV) | ffmpeg via `pydub`/`soundfile` | Reject over 15 min in v1 |
| 1b | **MIDI input shortcut** | `mido` / `pretty_midi` | Skip stages 2–3; notes are already exact. Use the MIDI's track/program info for instruments |
| 2 | Stem separation | **Demucs** (htdemucs / htdemucs_6s, which includes guitar & piano stems) | Skippable for solo recordings |
| 3 | Note transcription (onset, offset, pitch, velocity, pitch bends) | **MuScriptor** (open-weight multi-instrument; can be conditioned to transcribe one instrument) | **Spotify Basic Pitch** run on each separated stem (lightweight, works without a GPU) |
| 4 | Tempo, beats, downbeats, time signature, key | `madmom` or `beat_this`; key via `essentia` or a `music21` key analyzer | Let the user override the BPM/time signature in the editor |
| 5 | Chord labels (per beat / per bar) | Build chords from the transcribed notes with `music21` chordify + a template matcher | Recognize chords from the audio directly (e.g., madmom's chord recognizer) as a cross-check |
| 6 | Instrument mapping & transposition | Custom (§5.3) | — |
| 7 | Fret + finger assignment | Custom solver (§5.1, §5.2) | — |
| 8 | Quantize to a rhythmic grid | Custom: snap onsets to the beat grid (1/16 or triplets), merge tied notes | Let the user change the quantize level in the UI |

Each stage writes its intermediate output (useful for debugging and for rerunning later stages only). If the user changes the tuning or the instrument, **only stages 6–8 rerun**, which should be fast (under 2 s).

> ⚠️ Verify licenses before shipping: Demucs (MIT), Basic Pitch (Apache-2.0) and alphaTab (MPL-2.0) are fine for commercial use. **Check MuScriptor's weights license** before relying on it in production.

## 4. Data model: `TabiffyScore` (JSON)

```jsonc
{
  "version": 1,
  "meta": { "title": "", "artist": "", "sourceFile": "", "bpm": 120, "timeSignature": [4,4], "key": "E minor" },
  "tempoMap": [{ "tick": 0, "bpm": 120 }],
  "ticksPerQuarter": 960,
  "chords": [{ "tick": 0, "durationTicks": 3840, "symbol": "Em", "pcs": [4,7,11], "confidence": 0.82 }],
  "tracks": [{
    "id": "t1",
    "name": "Guitar 1",
    "sourceInstrument": "guitar",          // what was detected in the audio
    "targetInstrument": "guitar",          // "guitar" | "bass" | "piano"
    "tuning": ["E2","A2","D3","G3","B3","E4"], // low → high
    "capo": 0,
    "transposeSemitones": 0,
    "notes": [{
      "id": "n1",
      "tick": 0, "durationTicks": 480,
      "midi": 52, "velocity": 90,
      "string": 5, "fret": 2,              // guitar only; 1 = high E
      "finger": 2,                         // 0 = open, 1–4 = index…pinky, "T" = thumb (optional)
      "techniques": ["bend:+2", "slide", "hammer", "pull", "vibrato", "palmMute"],
      "confidence": 0.74,
      "userEdited": false
    }]
  }]
}
```

- Piano tracks use `hand` ("L"/"R") and `finger` (1–5, thumb = 1, which is standard piano fingering) instead of string/fret.
- Mark low-confidence notes (below ~0.5) in the UI so users know where to check.

## 5. Core algorithms

### 5.1 Fret/position solver (guitar & bass)
Group notes into **time slices** (notes that start within ±30 ms of each other become one chord). For each slice, list every **candidate voicing**: each note placed on one string+fret, one note per string, frets 0–24, within the tuning and capo.

Run **Viterbi / dynamic programming** across the slices to minimize total cost:

- **Within one voicing:** fret span (penalize stretches over 4 frets heavily, over 5 is impossible unless open strings are involved), how many fingers are needed (over 4 fretted notes needs a barre), skipped strings in strummed chords, and high frets (a light penalty).
- **Between voicings:** how far the hand moves (|Δ hand position|), bigger penalties for big jumps during fast passages (scale by the time gap), and a small bonus for staying in one position.
- **Preferences:** a bias toward open strings (user setting), a bias toward standard "cowboy" chord shapes when the chord label matches a known shape (keep a lookup table of common shapes such as CAGED and power chords).

Process the song in windows (e.g., 8 bars, overlapping) so long songs stay fast. Expose the cost weights in a config file so they're easy to tune.

### 5.2 Finger assignment (1–4)
Given the chosen voicings and a hand **position** (the fret under the index finger):
- Default rule: finger = fret − position + 1, kept between 1 and 4; open strings = 0.
- **Barre detection:** several notes on the same fret across neighboring strings at the lowest fretted fret → finger 1 barre.
- Stretches: allow finger 4 to reach position+4 when nothing else needs it; mark the stretch.
- Moving between neighboring slices: prefer keeping the same finger on a note that's held and keeping a **guide finger** on its string during slides.
- Second DP pass (optional, v1.1): minimize finger changes across slices.

Piano fingering (v1.1): a simple rule-based DP using standard piano fingering costs (thumb passing under, how far the hand stretches). v1 can show only which hand (L/R).

### 5.3 Instrument mapping & transposition
- **Source = guitar → target = guitar:** keep the pitches; run the solver.
- **Source = other instrument → guitar/bass/piano:** take one track or merge several the user picks; **shift by octaves** into the target's range (guitar E2–E6 in standard tuning, bass E1–G3, piano A0–C8). Shift whole phrases, not single notes, so the melody keeps its shape. Pick the octave shift that keeps the most notes in range; flag notes that are still out of range.
- **Reduce dense parts for guitar:** if a slice has more than 6 notes (or no playable voicing exists), keep the bass note + melody (top note) + chord tones, in that order of priority.
- **Key transposition:** the user can transpose ±12 semitones. Also suggest a capo position ("Capo 2, play in G shapes"), chosen by running the solver for each capo 0–7 and picking the lowest cost.

### 5.4 Chord labeling
For each beat, collect the pitch classes that are sounding (weighted by duration × velocity) and match them against chord templates (maj, min, 7, maj7, m7, sus2, sus4, dim, aug, add9, power/5) to get a root + quality. Smooth the labels with an HMM or a minimum-duration rule so chord names don't flicker. Show slash chords when the bass note isn't the root.

## 6. Frontend

### 6.1 Score view & player (alphaTab)
- Use `@coderline/alphatab` to draw standard notation + tab, chord names above the staff, and chord diagrams.
- Playback with alphaSynth (alphaTab's built-in player) and a SoundFont; controls for tempo (25–150%), looping a selection, metronome / count-in, and solo/mute per track.
- **Original-audio sync mode:** play the uploaded audio with the cursor moving in sync (alphaTab supports syncing to an outside audio player), with a toggle between the original audio and the synthesized version.

### 6.2 Instrument visualizer
- **Fretboard component** (SVG or Canvas): the current tuning is labeled at the nut, the capo is drawn, the notes playing now light up with **finger numbers 1–4** inside the dots, upcoming notes appear ghosted, and barres are drawn as a bar. Option to flip it for left-handed players.
- **Piano component:** an 88-key keyboard (auto-zooms to the range in use); the notes playing now light up, colored by hand, with finger numbers.
- Both are driven by alphaTab's playback position events → find the notes active at the current tick in `TabiffyScore`.

### 6.3 Tab editor (required in v1)
Because transcription is never perfect, the editor is a core feature:
- Click a note → change the string/fret (the pitch updates automatically), the finger, the duration, techniques, or delete it.
- Add notes/rests from the keyboard (number keys type frets, arrow keys move between strings and beats, like Guitar Pro).
- **Same pitch, different position:** a selected note can be moved to another string while keeping its pitch; the solver re-optimizes the fingering around it.
- Edit the chord name per bar; change the tempo or time signature; insert or delete bars.
- Undo/redo (command pattern), autosave the `TabiffyScore` to the backend.
- Notes the user has edited are **locked**: when the solver reruns (e.g., after a tuning change) it keeps them fixed.
- Highlight low-confidence notes and add a "review next uncertain note" button.

### 6.4 Settings
- Tunings: Standard, Drop D, D Standard, Eb Standard, DADGAD, Open G, Open D, Open E, 7-string B standard, 4/5-string bass, plus custom tunings.
- Capo 0–12, instrument target, open-string preference, max fret, difficulty ("simplify chords" reduces voicings to 3–4 notes).

## 7. Exports
| Format | How |
|--------|-----|
| **Guitar Pro (.gp, GP7/8)** | alphaTab's GP7 exporter (`alphaTab.exporter.Gp7Exporter`), client-side. alphaTab reads `.gpx` (GP6) but **does not write** it; `.gp` is the modern format and opens in Guitar Pro 7/8, MuseScore 4 and TuxGuitar (check which versions). |
| **MIDI (.mid)** | alphaTab's MIDI export, or generate it on the server with `pretty_midi` from `TabiffyScore` (one track per instrument, correct GM programs, tempo map). |
| **PDF** | v1: a print stylesheet on the alphaTab view (page layout mode) → `window.print()`. v1.1: server-side headless Chromium (Playwright) running the same view for consistent, paginated PDFs with a title page and chord-diagram legend. |
| (Bonus) MusicXML | `music21` on the server, so users can open the music in notation programs. |

## 8. Backend API (sketch)
```
POST   /api/jobs                 multipart upload → { jobId }
GET    /api/jobs/{id}            { status, stage, progress, error }
GET    /api/jobs/{id}/events     SSE progress stream
GET    /api/scores/{id}          TabiffyScore
PUT    /api/scores/{id}          save edits (full doc; v2 could send only the changes)
POST   /api/scores/{id}/resolve  { trackId, tuning, capo, target, transpose, lockedNoteIds } → re-run stages 6–8
GET    /api/scores/{id}/export?format=pdf|mid|musicxml
```

## 9. Milestones (build in this order)
1. **M0 — Skeleton:** monorepo (`/backend` FastAPI, `/frontend` Vite+React+TS), Docker Compose (api, worker, redis, postgres), CI with lint + tests.
2. **M1 — MIDI → tab (no ML):** upload a .mid → `TabiffyScore` → fret/finger solver → alphaTab view + playback + .gp/.mid export. *This proves the hardest custom part (the solver) without transcription noise.*
3. **M2 — Audio → notes:** Basic Pitch on solo-instrument recordings; quantization; tempo/key detection.
4. **M3 — Full songs:** Demucs stems + MuScriptor; pick which instrument/track to tab.
5. **M4 — Visualizers:** animated fretboard + piano synced to playback; tuning/capo display; finger numbers.
6. **M5 — Editor:** the full tab editor (§6.3), locked notes, re-solve.
7. **M6 — Transposition & other instruments:** §5.3, capo suggestions, piano hand assignment, PDF via headless Chromium.
8. **M7 — Polish:** accounts, saved library, sharing, piano fingering DP.

## 10. Testing & evaluation
- **Unit tests:** solver (known riffs → expected fingering, e.g., open C chord, E-shape barre at fret 5, a pentatonic box), chord labeler (templates), quantizer, octave mapping.
- **Round trip:** `TabiffyScore` → .gp → re-import with alphaTab → same notes.
- **Transcription accuracy:** run `mir_eval` note F1 on GuitarSet (guitar) and MAESTRO (piano) samples; track the scores in CI as a nightly job.
- **Playability metric:** average fret span and position shifts per bar, compared with human tabs from the GuitarSet annotations.
- Golden test files: put 5–10 short, rights-cleared clips in `/fixtures`.

## 11. Risks & open questions
- **Transcription accuracy on full mixes is still limited** (the newest open model scores about 48 F1 on standard benchmarks). Set expectations in the UI; the editor is the fix for this.
- GPU cost/latency for Demucs + MuScriptor: decide between a hosted GPU worker and running on CPU with a queue (minutes per song).
- Copyright: users upload commercial recordings. Need terms of service, no public sharing of transcriptions of copyrighted songs without a policy, and a takedown process.
- Piano fingering standard: use 1–5 (thumb = 1)? *Assumed yes.*
- Guitar thumb-over notes ("T"): support in v1 or later?
- Left-handed display, 7/8-string and bass support: v1 or later?
- Licensing of MuScriptor weights (see §3).
