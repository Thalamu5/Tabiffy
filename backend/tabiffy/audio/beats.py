"""Stage 4: tempo, beats, downbeats and meter from audio (librosa).

Downbeats are guessed from where low-frequency (bass/kick) accents fall; the meter is
4/4 unless 3/4 fits clearly better. Users can fix both in the app (half/double tempo,
shift bar lines, change time signature).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

SR = 22050
HOP = 512


@dataclass
class BeatInfo:
    """Beat times (seconds), tempo and meter found in a recording."""

    bpm: float
    beat_times: list[float] = field(default_factory=list)
    beats_per_bar: int = 4
    downbeat_index: int = 0  # index into beat_times of the first downbeat

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> BeatInfo:
        return cls(**d)


def meter_and_downbeat(accents: np.ndarray) -> tuple[int, int]:
    """Pick beats-per-bar (3 or 4) and the phase of the downbeat from per-beat accents."""
    if len(accents) < 8:
        return 4, 0
    a = accents / (accents.mean() + 1e-9)
    best: dict[int, tuple[float, int]] = {}
    for m in (4, 3):
        scores = [float(a[p::m].mean()) for p in range(m)]
        phase = int(np.argmax(scores))
        best[m] = (scores[phase] - float(np.mean([s for i, s in enumerate(scores) if i != phase])), phase)
    m = 3 if best[3][0] > best[4][0] * 1.25 and best[3][0] > 0.15 else 4
    return m, best[m][1]


def _norm(x: np.ndarray) -> np.ndarray:
    return x / (x.mean() + 1e-9)


def downbeat_accents(y: np.ndarray, sr: int, frames: np.ndarray) -> np.ndarray:
    """How "downbeat-like" each beat is: loud low end (kick/bass) + a change of harmony."""
    import librosa

    spec = np.abs(librosa.stft(y, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=sr)
    low = spec[freqs < 150].sum(axis=0)
    low_at = np.array([low[f : f + 4].mean() if f < len(low) else 0.0 for f in frames])

    chroma = librosa.feature.chroma_stft(S=spec**2, sr=sr)
    bounds = list(frames) + [chroma.shape[1]]
    per_beat = np.stack(
        [chroma[:, a : max(a + 1, b)].mean(axis=1) for a, b in zip(bounds[:-1], bounds[1:], strict=True)]
    )
    unit = per_beat / (np.linalg.norm(per_beat, axis=1, keepdims=True) + 1e-9)
    change = np.zeros(len(frames))
    change[1:] = 1.0 - np.sum(unit[1:] * unit[:-1], axis=1)
    return _norm(low_at) + _norm(change + 1e-3)


def detect_beats(wav_path: Path) -> BeatInfo:
    """Find the beats, tempo, meter and first downbeat of a recording with librosa."""
    import librosa

    y, sr = librosa.load(str(wav_path), sr=SR, mono=True)
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    tempo, frames = librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=HOP, trim=False)
    bpm = float(np.atleast_1d(tempo)[0]) if np.size(tempo) else 120.0
    frames = np.asarray(frames, dtype=int)
    if len(frames) < 4 or bpm <= 0:
        return BeatInfo(bpm=120.0, beat_times=[i * 0.5 for i in range(int(len(y) / sr / 0.5) + 2)])
    times = librosa.frames_to_time(frames, sr=sr, hop_length=HOP)
    accents = downbeat_accents(y, sr, frames)
    m, phase = meter_and_downbeat(accents)
    beat_bpm = 60.0 / float(np.median(np.diff(times)))
    return BeatInfo(
        bpm=round(beat_bpm, 2), beat_times=[round(float(t), 4) for t in times], beats_per_bar=m, downbeat_index=phase
    )
