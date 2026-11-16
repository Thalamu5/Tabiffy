"""Audio import: decode -> transcribe -> beats -> TabiffyScore.

Intermediate outputs are written to `work_dir` so later steps can re-run cheaply:
  decoded.wav (deleted afterwards), audio.mp3, 3_notes.json (seconds), 4_beats.json
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from ..key_detect import detect_key
from ..models import AudioInfo, Meta, Note, SolverSettings, TabiffyScore, TempoPoint, Track
from ..pipeline import solve_all
from .beats import BeatInfo, detect_beats
from .decode import decode
from .grid import BeatGrid
from .legato import find_links
from .transcribe import SILENCE_RMS, RawNote, confidence, remove_drums, stem_rms, transcribe

log = logging.getLogger(__name__)

TPQ = 960
STEM_LABEL = {
    "guitar": "Guitar",
    "bass": "Bass",
    "piano": "Piano",
    "vocals": "Vocals (melody)",
    "other": "Other instruments",
    "mix": "Full mix",
}
SOURCE_PROGRAM = {"guitar": 25, "bass": 33, "piano": 0, "vocals": 54, "other": 48}
MIN_NOTES = 8

Stage = Callable[[str, float], None]


def _noop(_name: str, _progress: float) -> None:
    pass


def transcribe_audio(input_path: Path, work_dir: Path, mode: str = "guitar", on_stage: Stage = _noop) -> AudioInfo:
    """Stages 1, 3, 4. The whole file is transcribed as one part (`mode` = what's in it).

    Tabiffy doesn't separate instruments itself: to tab one instrument from a band recording,
    separate it first with a tool of your choice and upload that part.
    Writes 3_notes.json and 4_beats.json into work_dir; returns audio info.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    on_stage("decode", 0.02)
    wav = work_dir / "decoded.wav"
    duration = decode(input_path, wav, work_dir / "audio.mp3")

    on_stage("transcribe", 0.15)
    notes: dict[str, list[dict]] = {}
    if stem_rms(wav) >= SILENCE_RMS:
        source_wav = remove_drums(wav, work_dir / "harmonic.wav") if mode == "mix" else wav
        found = transcribe(source_wav, mode)
        if len(found) >= MIN_NOTES:
            notes[mode] = [n.to_dict() for n in found]
    if not notes:
        warnings.append("No clear notes were found in this recording.")

    on_stage("beats", 0.85)
    beats = detect_beats(wav)
    (work_dir / "3_notes.json").write_text(json.dumps(notes))
    (work_dir / "4_beats.json").write_text(json.dumps(beats.to_dict()))
    return AudioInfo(duration_seconds=round(duration, 3), mode=mode, detected_bpm=beats.bpm, warnings=warnings)


def build_source(
    work_dir: Path, audio: AudioInfo, title: str, source_file: str, beats_per_bar: int | None = None
) -> TabiffyScore:
    """Turn the stored notes (seconds) into a beat-aligned source score."""
    notes_by_stem: dict[str, list[dict]] = json.loads((work_dir / "3_notes.json").read_text())
    beats = BeatInfo.from_dict(json.loads((work_dir / "4_beats.json").read_text()))
    beats = align_beats(beats, [RawNote(**d).start for raw in notes_by_stem.values() for d in raw])
    grid = BeatGrid(beats, audio.duration_seconds, TPQ, audio.tempo_factor, audio.downbeat_shift, beats_per_bar)

    tracks: list[Track] = []
    counter = 0
    for name, raw in notes_by_stem.items():
        out: list[Note] = []
        raws = [RawNote(**d) for d in raw]
        for n in raws:
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
        if instrument in LEGATO_INSTRUMENTS:
            mark_legato(raws, out)
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


ALIGN_WINDOW = 0.07  # seconds: a note this close to a beat counts as played on that beat


def align_beats(beats: BeatInfo, starts: list[float]) -> BeatInfo:
    """Shift the beat times so they line up with the notes played on them. The beat tracker and the
    note detector can disagree by a few hundredths of a second, which is enough to push fast notes
    (like 16th-note triplets) onto the wrong grid line."""
    import numpy as np

    if not starts or not beats.beat_times:
        return beats
    s = np.sort(np.asarray(starts))
    offsets = []
    for b in beats.beat_times:
        k = int(np.searchsorted(s, b))
        near = [s[i] - b for i in (k - 1, k) if 0 <= i < len(s) and abs(s[i] - b) <= ALIGN_WINDOW]
        if near:
            offsets.append(min(near, key=abs))
    # Only trust a shift that many beats agree on.
    if len(offsets) < max(4, len(beats.beat_times) // 4):
        return beats
    shift = float(np.median(offsets))
    if abs(shift) < 0.005:
        return beats
    return BeatInfo(
        bpm=beats.bpm,
        beat_times=[max(0.0, t + shift) for t in beats.beat_times],
        beats_per_bar=beats.beats_per_bar,
        downbeat_index=beats.downbeat_index,
    )


LEGATO_INSTRUMENTS = {"guitar", "bass"}  # slides / hammer-ons / pull-offs only make sense on strings


def mark_legato(raws: list[RawNote], notes: list[Note]) -> None:
    """Copy slide / hammer-on / pull-off links found in the audio onto the notes (same order as `raws`)."""
    for link in find_links(raws):
        first = notes[link.first]
        first.techniques = [link.technique]
        first.legato_to = notes[link.second].id
        if not link.sure:
            first.flags = [*first.flags, "suggestedTechnique"]


def import_audio(
    input_path: Path,
    work_dir: Path,
    filename: str,
    mode: str = "guitar",
    settings: SolverSettings | None = None,
    on_stage: Stage = _noop,
    tuning: str = "auto",
) -> tuple[TabiffyScore, TabiffyScore]:
    audio = transcribe_audio(input_path, work_dir, mode, on_stage)
    on_stage("solve", 0.95)
    title = Path(filename).stem.replace("_", " ")
    source = build_source(work_dir, audio, title, filename)
    out = solve_all(source, settings, tuning=tuning)
    cleanup(work_dir)
    return source, out


def cleanup(work_dir: Path) -> None:
    """Delete the large decoded WAV; notes, beats and the MP3 are all later steps need."""
    for name in ("decoded.wav", "harmonic.wav"):
        (work_dir / name).unlink(missing_ok=True)


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
