"""Stage 4 (key part): Krumhansl-Schmuckler key estimation from notes."""

from __future__ import annotations

import numpy as np

from .models import Note
from .pitch import pc_name

_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_FLAT_KEYS_MAJOR = {5, 10, 3, 8, 1}  # F Bb Eb Ab Db
_FLAT_KEYS_MINOR = {2, 7, 0, 5, 10}  # Dm Gm Cm Fm Bbm


def detect_key(notes: list[Note]) -> str:
    hist = np.zeros(12)
    for n in notes:
        hist[n.midi % 12] += n.duration_ticks
    if hist.sum() == 0:
        return ""
    best = ("", -2.0)
    for tonic in range(12):
        modes = ((_MAJOR, "major", _FLAT_KEYS_MAJOR), (_MINOR, "minor", _FLAT_KEYS_MINOR))
        for profile, mode, flat_set in modes:
            r = float(np.corrcoef(hist, np.roll(profile, tonic))[0, 1])
            if r > best[1]:
                best = (f"{pc_name(tonic, tonic in flat_set)} {mode}", r)
    return best[0]
