"""Stage 5: chord labels from notes (SPEC 5.4).

For every beat we build a pitch-class profile (overlap duration x velocity), score
it against chord templates, then run Viterbi with a chord-change penalty so labels
don't flicker. Slash chords are emitted when the lowest sounding note isn't the root.
"""

from __future__ import annotations

import numpy as np

from .models import ChordLabel, Note
from .pitch import pc_name

# quality suffix -> intervals, small complexity penalty (prefer simple chords)
TEMPLATES: dict[str, tuple[tuple[int, ...], float]] = {
    "": ((0, 4, 7), 0.0),
    "m": ((0, 3, 7), 0.0),
    "5": ((0, 7), 0.08),
    "7": ((0, 4, 7, 10), 0.05),
    "maj7": ((0, 4, 7, 11), 0.05),
    "m7": ((0, 3, 7, 10), 0.05),
    "sus2": ((0, 2, 7), 0.07),
    "sus4": ((0, 5, 7), 0.07),
    "dim": ((0, 3, 6), 0.07),
    "aug": ((0, 4, 8), 0.1),
    "add9": ((0, 2, 4, 7), 0.08),
}
NO_CHORD = "N"
CHANGE_PENALTY = 0.35
MIN_WEIGHT = 1e-6
# flats for these roots read more naturally
_FLAT_ROOTS = {1, 3, 8, 10}


def _labels() -> list[tuple[str, int, tuple[int, ...], float]]:
    out = []
    for root in range(12):
        for q, (iv, pen) in TEMPLATES.items():
            out.append((q, root, tuple((root + i) % 12 for i in iv), pen))
    return out


LABELS = _labels()


def _template_scores(profile: np.ndarray, bass_pc: int = -1) -> np.ndarray:
    """Score in [-1, 1] for each label plus NO_CHORD (last entry)."""
    total = profile.sum()
    scores = np.empty(len(LABELS) + 1)
    # A single sounding pitch class (e.g. one melody note) isn't a chord.
    if total < MIN_WEIGHT or int((profile / max(total, MIN_WEIGHT) > 0.12).sum()) < 2:
        scores[:] = -1.0
        scores[-1] = 1.0
        return scores
    p = profile / total
    for i, (_, root, pcs, pen) in enumerate(LABELS):
        inside = sum(p[pc] for pc in pcs)
        # template tones that aren't sounding (a missing fifth counts half)
        missing = sum(0.5 if pc == (root + 7) % 12 else 1.0 for pc in pcs if p[pc] < 0.03) / len(pcs)
        root_bonus = 0.05 if p[root] > 0.1 else -0.15
        bass_bonus = 0.1 if root == bass_pc else 0.0
        scores[i] = inside - (1 - inside) - 0.6 * missing + root_bonus + bass_bonus - pen
    scores[-1] = -0.2
    return scores


def label_chords(
    notes: list[Note], tpq: int, beats_per_bar: int = 4, beat_ticks: int | None = None
) -> list[ChordLabel]:
    if not notes:
        return []
    beat = beat_ticks or tpq
    end = max(n.tick + n.duration_ticks for n in notes)
    n_beats = max(1, -(-end // beat))
    profiles = np.zeros((n_beats, 12))
    bass = np.full(n_beats, -1)
    bass_pitch = np.full(n_beats, 999)
    for n in notes:
        b0, b1 = n.tick // beat, (n.tick + n.duration_ticks - 1) // beat
        for b in range(b0, min(b1, n_beats - 1) + 1):
            overlap = min(n.tick + n.duration_ticks, (b + 1) * beat) - max(n.tick, b * beat)
            if overlap <= 0:
                continue
            profiles[b, n.midi % 12] += overlap * (n.velocity / 127)
            if n.midi < bass_pitch[b]:
                bass_pitch[b], bass[b] = n.midi, n.midi % 12

    # A beat where notes never overlap (a single-note line) gets no chord.
    poly = np.zeros(n_beats, dtype=int)
    starts = np.sort([n.tick for n in notes])
    ends = np.sort([n.tick + n.duration_ticks for n in notes])
    for n in notes:
        b0, b1 = n.tick // beat, min((n.tick + n.duration_ticks - 1) // beat, n_beats - 1)
        sounding = int(np.searchsorted(starts, n.tick, "right") - np.searchsorted(ends, n.tick, "right"))
        poly[b0 : b1 + 1] = np.maximum(poly[b0 : b1 + 1], sounding)

    emis = np.array([_template_scores(p, int(b)) for p, b in zip(profiles, bass, strict=True)])  # (beats, labels)
    emis[poly < 2, :-1] = -1.0
    emis[poly < 2, -1] = 1.0
    n_lab = emis.shape[1]
    # Viterbi (maximize): score + -CHANGE_PENALTY on label change
    dp = emis[0].copy()
    back = np.zeros((n_beats, n_lab), dtype=int)
    for b in range(1, n_beats):
        best_prev = int(np.argmax(dp))
        stay = dp
        switch = dp[best_prev] - CHANGE_PENALTY
        use_switch = switch > stay
        back[b] = np.where(use_switch, best_prev, np.arange(n_lab))
        dp = np.where(use_switch, switch, stay) + emis[b]
    path = [int(np.argmax(dp))]
    for b in range(n_beats - 1, 0, -1):
        path.append(int(back[b, path[-1]]))
    path.reverse()

    labels: list[ChordLabel] = []
    b = 0
    while b < n_beats:
        lab = path[b]
        e = b
        while e + 1 < n_beats and path[e + 1] == lab:
            e += 1
        if lab != n_lab - 1:
            q, root, pcs, _ = LABELS[lab]
            seg_bass = [int(x) for x in bass[b : e + 1] if x >= 0]
            symbol = pc_name(root, root in _FLAT_ROOTS) + q
            if seg_bass:
                common_bass = max(set(seg_bass), key=seg_bass.count)
                if common_bass != root and common_bass in pcs and q != "5":
                    symbol += "/" + pc_name(common_bass, root in _FLAT_ROOTS)
            conf = float(np.clip(np.mean(emis[b : e + 1, lab]), 0, 1))
            labels.append(
                ChordLabel(
                    tick=b * beat,
                    duration_ticks=(e - b + 1) * beat,
                    symbol=symbol,
                    pcs=sorted(set(pcs)),
                    confidence=round(conf, 3),
                )
            )
        b = e + 1
    return labels
