"""Synthesize small test recordings with known notes (no copyright, no binary fixtures)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

SR = 44100


def midi_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def pluck(midi: int, seconds: float, rng: np.random.Generator, decay: float = 0.996, bright: float = 0.5) -> np.ndarray:
    """Karplus-Strong plucked string."""
    n = int(seconds * SR)
    period = max(2, int(round(SR / midi_hz(midi))))
    buf = rng.uniform(-1, 1, period) * bright + rng.uniform(-1, 1, period) * (1 - bright) * 0.3
    out = np.empty(n)
    for i in range(n):
        out[i] = buf[i % period]
        buf[i % period] = decay * 0.5 * (buf[i % period] + buf[(i + 1) % period])
    fade = np.ones(n)
    k = min(n, int(0.02 * SR))
    fade[-k:] = np.linspace(1, 0, k)
    return out * fade


def kick(seconds: float = 0.25) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return np.sin(2 * np.pi * (50 + 80 * np.exp(-t * 30)) * t) * np.exp(-t * 12)


def place(track: np.ndarray, sound: np.ndarray, at: float, gain: float = 1.0) -> None:
    i = int(at * SR)
    j = min(len(track), i + len(sound))
    if i < len(track):
        track[i:j] += sound[: j - i] * gain


def band(
    bpm: float = 100.0, bars: int = 8, seed: int = 0
) -> tuple[dict[str, np.ndarray], list[tuple[float, float, int]]]:
    """Returns stems {'guitar','bass','drums'} and the guitar's true notes (start, end, midi)."""
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    total = bars * 4 * beat + 1.0
    n = int(total * SR)
    stems = {k: np.zeros(n) for k in ("guitar", "bass", "drums")}
    chords = {"C": [48, 52, 55, 60, 64], "G": [43, 47, 50, 55, 59], "Am": [45, 52, 57, 60, 64], "F": [41, 48, 53, 57]}
    roots = {"C": 36, "G": 31, "Am": 33, "F": 29}
    truth: list[tuple[float, float, int]] = []
    for b in range(bars):
        name = ["C", "G", "Am", "F"][b % 4]
        for beat_i in range(4):
            t = (b * 4 + beat_i) * beat
            place(stems["drums"], kick(), t, 1.0 if beat_i == 0 else 0.45)
            place(stems["bass"], pluck(roots[name], beat * 0.95, rng, 0.997, 0.2), t, 0.6)
            if beat_i in (0, 2):  # strum on beats 1 and 3
                for k, m in enumerate(chords[name]):
                    start = t + k * 0.012
                    place(stems["guitar"], pluck(m, beat * 2 * 0.95, rng), start, 0.35)
                    truth.append((start, start + beat * 2 * 0.95, m))
    return stems, truth


def write(path: Path, audio: np.ndarray) -> Path:
    import soundfile as sf

    peak = np.max(np.abs(audio)) or 1.0
    sf.write(str(path), (audio / peak * 0.8).astype(np.float32), SR)
    return path
