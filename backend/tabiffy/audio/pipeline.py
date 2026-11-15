"""Audio import: decode -> separate -> transcribe -> beats -> TabiffyScore.

Intermediate outputs are written to `work_dir` so later steps can re-run cheaply:
  decoded.wav, audio.mp3, stems/*.wav, 3_notes.json (seconds), 4_beats.json
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path

from ..key_detect import detect_key
from ..models import AudioInfo, Meta, Note, SolverSettings, TabiffyScore, TempoPoint, Track
from ..pipeline import solve_all
from . import separate as sep
from .beats import BeatInfo, detect_beats
from .decode import decode
from .grid import BeatGrid
from .transcribe import RawNote, confidence, stem_rms, transcribe

log = logging.getLogger(__name__)

TPQ = 960
STEM_ORDER = ["guitar", "bass", "piano", "vocals", "other"]
STEM_LABEL = {
    "guitar": "Guitar",
    "bass": "Bass",
    "piano": "Piano",
    "vocals": "Vocals (melody)",
    "other": "Other instruments",
    "mix": "Full mix",
}
SOURCE_PROGRAM = {"guitar": 25, "bass": 33, "piano": 0, "vocals": 54, "other": 48}
MIN_NOTES_PER_STEM = 8
SOLO_MODES = {"guitar", "bass", "piano", "other"}

Stage = Callable[[str, float], None]


def _noop(_name: str, _progress: float) -> None:
    pass


def transcribe_audio(input_path: Path, work_dir: Path, mode: str = "full", on_stage: Stage = _noop) -> AudioInfo:
    """Stages 1-4. Writes 3_notes.json and 4_beats.json into work_dir; returns audio info."""
    work_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    on_stage("decode", 0.02)
    wav = work_dir / "decoded.wav"
    duration = decode(input_path, wav, work_dir / "audio.mp3")

    stems: dict[str, Path]
    separated = False
    if mode in SOLO_MODES:
        stems = {mode: wav}
    else:
        on_stage("separate", 0.05)
        try:
            stems = sep.separate(wav, work_dir / "stems", lambda f: on_stage("separate", 0.05 + 0.55 * f))
            separated = True
        except sep.SeparationUnavailable as e:
            log.warning("stem separation unavailable: %s", e)
            warnings.append(
                "Instrument separation (Demucs) wasn't available, so the full mix was transcribed "
                "as one part. Results will be rough."
            )
            stems = {"mix": wav}

    names = [s for s in STEM_ORDER if s in stems] + [s for s in stems if s not in STEM_ORDER and s != "drums"]
    notes: dict[str, list[dict]] = {}
    for i, name in enumerate(names):
        on_stage(f"transcribe:{name}", 0.6 + 0.3 * i / max(1, len(names)))
        if stem_rms(stems[name]) < 0.005:
            continue
        instrument = "other" if name == "mix" else name
        found = transcribe(stems[name], instrument)
        if len(found) >= MIN_NOTES_PER_STEM:
            notes[name] = [n.to_dict() for n in found]
    if not notes:
        warnings.append("No clear notes were found in this recording.")

    on_stage("beats", 0.92)
    beats = detect_beats(wav)
    (work_dir / "3_notes.json").write_text(json.dumps(notes))
    (work_dir / "4_beats.json").write_text(json.dumps(beats.to_dict()))
    return AudioInfo(
        duration_seconds=round(duration, 3), separated=separated, mode=mode, detected_bpm=beats.bpm, warnings=warnings
    )


def build_source(
    work_dir: Path, audio: AudioInfo, title: str, source_file: str, beats_per_bar: int | None = None
) -> TabiffyScore:
    """Turn the stored notes (seconds) into a beat-aligned source score."""
    notes_by_stem: dict[str, list[dict]] = json.loads((work_dir / "3_notes.json").read_text())
    beats = BeatInfo.from_dict(json.loads((work_dir / "4_beats.json").read_text()))
    grid = BeatGrid(beats, audio.duration_seconds, TPQ, audio.tempo_factor, audio.downbeat_shift, beats_per_bar)

    tracks: list[Track] = []
    counter = 0
    for name, raw in notes_by_stem.items():
        out: list[Note] = []
        for d in raw:
            n = RawNote(**d)
            tick = max(0, grid.tick(n.start))
            dur = max(TPQ // 16, grid.tick(n.end) - tick)
            counter += 1
            out.append(
                Note(
                    id=f"n{counter}",
                    tick=tick,
                    duration_ticks=dur,
                    midi=n.pitch,
                    velocity=int(max(30, min(127, n.amplitude * 160))),
                    confidence=confidence(n.amplitude, n.end - n.start),
                )
            )
        instrument = name if name in ("guitar", "bass", "piano", "vocals") else "other"
        tracks.append(
            Track(
                id=f"src{len(tracks) + 1}",
                name=STEM_LABEL.get(name, name.title()),
                source_instrument=instrument,
                target_instrument="bass" if instrument == "bass" else "guitar",
                program=SOURCE_PROGRAM.get(instrument, 0),
                notes=out,
                source_track_index=len(tracks),
            )
        )

    audio = audio.model_copy(update={"sync_points": grid.sync_points()})
    all_notes = [n for t in tracks for n in t.notes]
    return TabiffyScore(
        meta=Meta(
            title=title,
            source_file=source_file,
            bpm=grid.bpm,
            time_signature=(grid.beats_per_bar, 4),
            key=detect_key(all_notes) if all_notes else "",
        ),
        tempo_map=[TempoPoint(tick=0, bpm=grid.bpm)],
        ticks_per_quarter=TPQ,
        tracks=tracks,
        audio=audio,
    )


def import_audio(
    input_path: Path,
    work_dir: Path,
    filename: str,
    mode: str = "full",
    settings: SolverSettings | None = None,
    on_stage: Stage = _noop,
) -> tuple[TabiffyScore, TabiffyScore]:
    audio = transcribe_audio(input_path, work_dir, mode, on_stage)
    on_stage("solve", 0.95)
    title = Path(filename).stem.replace("_", " ")
    source = build_source(work_dir, audio, title, filename)
    out = solve_all(source, settings)
    cleanup(work_dir)
    return source, out


def cleanup(work_dir: Path) -> None:
    """Delete the large WAV intermediates; notes, beats and the MP3 are all later steps need."""
    if os.environ.get("TABIFFY_KEEP_STEMS"):
        return
    (work_dir / "decoded.wav").unlink(missing_ok=True)
    for p in (work_dir / "stems").glob("*.wav"):
        p.unlink()


def retime(
    work_dir: Path, current: TabiffyScore, tempo_factor: float, downbeat_shift: int, beats_per_bar: int
) -> tuple[TabiffyScore, TabiffyScore]:
    """Rebuild bars/beats with user overrides and re-solve every track with its current options."""
    assert current.audio is not None
    audio = current.audio.model_copy(update={"tempo_factor": tempo_factor, "downbeat_shift": downbeat_shift})
    source = build_source(work_dir, audio, current.meta.title, current.meta.source_file, beats_per_bar)
    source.meta.artist = current.meta.artist
    out = solve_all(source, current.settings, previous=current)
    return source, out
