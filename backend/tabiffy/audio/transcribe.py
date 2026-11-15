"""Stage 3: note transcription with Spotify's Basic Pitch (ONNX model, CPU friendly)."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class RawNote:
    start: float  # seconds
    end: float
    pitch: int
    amplitude: float  # Basic Pitch's note activation (0-1), used as confidence

    def to_dict(self) -> dict:
        return asdict(self)


# Per-instrument Basic Pitch settings: (min Hz, max Hz, onset threshold, frame threshold, min note ms)
PROFILES: dict[str, tuple[float | None, float | None, float, float, float]] = {
    "guitar": (75.0, 1400.0, 0.5, 0.3, 80.0),
    "bass": (28.0, 420.0, 0.45, 0.3, 90.0),
    "piano": (26.0, 4200.0, 0.5, 0.3, 60.0),
    "vocals": (80.0, 1100.0, 0.55, 0.35, 120.0),
    "other": (60.0, 2100.0, 0.55, 0.35, 90.0),
}
MONOPHONIC = {"vocals", "bass"}
SILENCE_RMS = 0.005  # stems quieter than this are treated as empty

_model = None


def _load_model():
    global _model
    if _model is None:
        import logging as _logging

        _logging.getLogger().setLevel(_logging.ERROR)  # basic-pitch warns about optional backends
        from basic_pitch import FilenameSuffix, build_icassp_2022_model_path
        from basic_pitch.inference import Model

        _logging.getLogger().setLevel(_logging.WARNING)
        _model = Model(build_icassp_2022_model_path(FilenameSuffix.onnx))
    return _model


def stem_rms(wav_path: Path) -> float:
    import numpy as np
    import soundfile as sf

    audio, _ = sf.read(str(wav_path), dtype="float32", always_2d=True)
    return float(np.sqrt(np.mean(audio**2))) if audio.size else 0.0


def keep_one_line(notes: list[RawNote], prefer: str) -> list[RawNote]:
    """Make a line monophonic: where notes overlap, keep the top (melody) or bottom (bass) one."""
    notes = sorted(notes, key=lambda n: n.start)
    out: list[RawNote] = []
    for n in notes:
        if out and n.start < out[-1].end - 0.03:
            prev = out[-1]
            better = n.pitch > prev.pitch if prefer == "top" else n.pitch < prev.pitch
            if abs(n.start - prev.start) < 0.05:
                if better or (n.pitch == prev.pitch and n.amplitude > prev.amplitude):
                    out[-1] = n
                continue
            prev.end = n.start  # the new note cuts the old one
        out.append(n)
    return [n for n in out if n.end - n.start > 0.04]


def transcribe(wav_path: Path, instrument: str) -> list[RawNote]:
    from basic_pitch.inference import predict

    lo, hi, onset, frame, min_ms = PROFILES.get(instrument, PROFILES["other"])
    _, _, events = predict(
        str(wav_path),
        _load_model(),
        onset_threshold=onset,
        frame_threshold=frame,
        minimum_note_length=min_ms,
        minimum_frequency=lo,
        maximum_frequency=hi,
        melodia_trick=True,
    )
    notes = [RawNote(float(s), float(e), int(p), float(a)) for s, e, p, a, *_ in events if e > s]
    if instrument in MONOPHONIC:
        notes = keep_one_line(notes, "top" if instrument == "vocals" else "bottom")
    return sorted(notes, key=lambda n: (n.start, n.pitch))


def confidence(amplitude: float, duration: float = 1.0) -> float:
    """A 0-1 guess at how likely a note is right (a heuristic, not a calibrated probability).

    Quiet notes (Basic Pitch amplitude, typically 0.15-0.8) and very short notes (often
    spurious onsets or bleed from other instruments) get lower scores.
    """
    loud = max(0.0, min(1.0, (amplitude - 0.12) / 0.4))
    long_enough = min(1.0, max(duration, 0.0) / 0.15) ** 0.5
    return round(loud * long_enough, 3)
