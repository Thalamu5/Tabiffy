"""Stage 3: note transcription with Spotify's Basic Pitch (ONNX model, CPU friendly)."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class RawNote:
    """One note heard in the recording, in seconds, before it is placed on the beat grid."""

    start: float  # seconds
    end: float
    pitch: int
    amplitude: float  # Basic Pitch's note activation (0-1), used as confidence
    # Clues for slides / hammer-ons / pull-offs (audio/legato.py). Defaults keep older stored notes valid.
    attack: float = 1.0  # pick-attack strength vs. this recording's typical picked note; low = legato
    glide_in: float = 0.0  # semitones the pitch glided from before the note began (negative = from below)

    def to_dict(self) -> dict:
        return asdict(self)


# Per-instrument Basic Pitch settings: (min Hz, max Hz, onset threshold, frame threshold, min note ms)
PROFILES: dict[str, tuple[float | None, float | None, float, float, float]] = {
    # down to ~40 Hz so drop tunings and 7/8-string low strings are heard (8-string F#1 = 46 Hz)
    "guitar": (40.0, 1400.0, 0.5, 0.3, 80.0),
    "bass": (28.0, 420.0, 0.45, 0.3, 90.0),
    "piano": (26.0, 4200.0, 0.5, 0.3, 60.0),
    "vocals": (80.0, 1100.0, 0.55, 0.35, 120.0),
    "other": (60.0, 2100.0, 0.55, 0.35, 90.0),
    # a whole band mix: wide range and more sensitive, since instruments mask each other
    "mix": (28.0, 4200.0, 0.4, 0.25, 80.0),
}
MONOPHONIC = {"vocals", "bass"}
SILENCE_RMS = 0.005  # recordings quieter than this are treated as empty

_model = None


def _load_model():
    """Load Basic Pitch's ONNX model once per process (it takes a moment)."""
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
    """Overall loudness of a WAV file, used to skip silent recordings."""
    import numpy as np
    import soundfile as sf

    audio, _ = sf.read(str(wav_path), dtype="float32", always_2d=True)
    return float(np.sqrt(np.mean(audio**2))) if audio.size else 0.0


def remove_drums(wav_path: Path, out_path: Path) -> Path:
    """Harmonic/percussive split (librosa HPSS): keeps sustained, pitched sound and drops most
    drum hits, which otherwise get transcribed as low notes. Used for full-mix uploads."""
    import librosa
    import numpy as np
    import soundfile as sf

    y, sr = librosa.load(str(wav_path), sr=22050, mono=True)
    harmonic = librosa.effects.harmonic(y, margin=2.0)
    sf.write(str(out_path), np.asarray(harmonic, dtype=np.float32), sr)
    return out_path


GHOST_RATIO = 0.5  # an octave-up note this much quieter than the note below is its overtone, not a note


def drop_octave_ghosts(notes: list[RawNote]) -> list[RawNote]:
    """Remove "ghost" notes: a quiet copy exactly one octave above a note starting at the same time.
    A string's strong 2nd harmonic causes these; real octaves are played about equally loud."""
    ghosts = set()
    by_start = sorted(range(len(notes)), key=lambda i: notes[i].start)
    for k, i in enumerate(by_start):
        lo = notes[i]
        for j in by_start[k + 1 :]:
            hi = notes[j]
            if hi.start - lo.start > 0.03:
                break
            for upper, lower, idx in ((hi, lo, j), (lo, hi, i)):
                if upper.pitch - lower.pitch == 12 and upper.amplitude < GHOST_RATIO * lower.amplitude:
                    ghosts.add(idx)
    return [n for i, n in enumerate(notes) if i not in ghosts]


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
    """Turn a recording into notes with Basic Pitch, using settings tuned for the instrument.
    Overtone ghosts are removed and each note gets its legato clues."""
    from basic_pitch.inference import predict

    lo, hi, onset, frame, min_ms = PROFILES.get(instrument, PROFILES["other"])
    output, _, events = predict(
        str(wav_path),
        _load_model(),
        onset_threshold=onset,
        frame_threshold=frame,
        minimum_note_length=min_ms,
        minimum_frequency=lo,
        maximum_frequency=hi,
        melodia_trick=True,
    )
    notes = drop_octave_ghosts([RawNote(float(s), float(e), int(p), float(a)) for s, e, p, a, *_ in events if e > s])
    add_legato_clues(notes, wav_path, output)
    if instrument in MONOPHONIC:
        notes = keep_one_line(notes, "top" if instrument == "vocals" else "bottom")
    return sorted(notes, key=lambda n: (n.start, n.pitch))


ATTACK_MIN_HZ = 3000  # a pick (or pluck) makes broadband noise up here; hammer-ons and slides barely do
GLIDE_LOOKBACK = 0.15  # seconds before a note's start searched for a slide arriving at it


def add_legato_clues(notes: list[RawNote], wav_path: Path, output: dict) -> None:
    """Fill in `attack` and `glide_in` for every note (see RawNote)."""
    import librosa
    import numpy as np
    from basic_pitch.note_creation import model_frames_to_time

    if not notes:
        return
    # Attack: the rise in high-frequency energy at each note start, relative to the recording's picked notes.
    y, sr = librosa.load(str(wav_path), sr=22050, mono=True)
    hop = 256
    spec = np.abs(librosa.stft(y, n_fft=1024, hop_length=hop)) ** 2
    high = spec[librosa.fft_frequencies(sr=sr, n_fft=1024) >= ATTACK_MIN_HZ]
    flux = librosa.onset.onset_strength(S=librosa.power_to_db(high + 1e-10), sr=sr, hop_length=hop)
    times = librosa.frames_to_time(np.arange(len(flux)), sr=sr, hop_length=hop)
    raw = []
    for n in notes:
        f = int(np.searchsorted(times, n.start))
        window = flux[max(0, f - 1) : f + 5]  # the attack peaks a few frames after the reported start
        raw.append(float(window.max()) if window.size else 0.0)
    typical = float(np.percentile(raw, 90)) or 1.0
    for n, r in zip(notes, raw, strict=True):
        # The first frames have nothing before them to rise from, so notes there count as picked.
        n.attack = 1.0 if n.start < 0.05 else round(min(1.0, r / typical), 3)

    # Glide: follow Basic Pitch's fine pitch track backwards from each start while it moves smoothly.
    contour = np.asarray(output["contour"])  # (frames, 3 bins per semitone from MIDI 21)
    ctimes = model_frames_to_time(contour.shape[0])
    for n in notes:
        n.glide_in = _glide_into(contour, ctimes, n)


def _glide_into(contour, ctimes, n: RawNote) -> float:
    """Semitones between where a smooth pitch slide started and this note (0 if it didn't slide in)."""
    import numpy as np

    f = int(np.searchsorted(ctimes, n.start))
    lo_bin = max(0, int((n.pitch - 12.5 - 21) * 3))
    hi_bin = min(contour.shape[1], int((n.pitch + 12.5 - 21) * 3))
    path: list[float] = []
    for fr in range(f, max(-1, int(np.searchsorted(ctimes, n.start - GLIDE_LOOKBACK)) - 1), -1):
        row = contour[fr, lo_bin:hi_bin]
        if row.size == 0 or row.max() < 0.12:
            break
        pitch = 21 + (lo_bin + int(np.argmax(row))) / 3
        if path and abs(pitch - path[-1]) > 1.0:  # a jump, not a glide
            break
        path.append(pitch)
    if not path:
        return 0.0
    # A real slide passes through in-between pitches, not just the start and end notes.
    origin = path[-1]
    between = sum(1 for p in path if min(abs(p - origin), abs(p - n.pitch)) > 0.5)
    return round(origin - n.pitch, 2) if between >= 2 else 0.0


def confidence(amplitude: float, duration: float = 1.0) -> float:
    """A 0-1 guess at how likely a note is right (a heuristic, not a calibrated probability).

    Quiet notes (Basic Pitch amplitude, typically 0.15-0.8) and very short notes (often
    spurious onsets or bleed from other instruments) get lower scores.
    """
    loud = max(0.0, min(1.0, (amplitude - 0.12) / 0.4))
    long_enough = min(1.0, max(duration, 0.0) / 0.15) ** 0.5
    return round(loud * long_enough, 3)
