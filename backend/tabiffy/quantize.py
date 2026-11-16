"""Stage 8: snap onsets/durations to a rhythmic grid.

The grid is chosen per quarter note: with triplets enabled, each beat uses the straight
1/16 grid, the 1/8-triplet grid (3 per beat) or the 1/16-triplet grid (6 per beat).
A small per-beat penalty for triplet grids and a cost for switching grids between
neighbouring beats keep loose straight playing straight, while real triplet passages
(consistent over several beats) keep their triplets. One grid per beat keeps the result
writable with standard note values.
"""

from __future__ import annotations

from .models import Note

GRIDS = {
    "1/8": [2],  # divisions per quarter note
    "1/16": [4],
    "1/32": [8],
    "1/16+triplets": [4, 3, 6],
}
# Timing error is measured in grid steps (0.5 = halfway between two grid lines). Per-beat penalty for
# each triplet grid; the 6-per-beat grid is finer, so it gets a bigger one.
TRIPLET_BIAS = {3: 0.3, 6: 0.6}
GRID_SWITCH = 0.1  # cost of changing grid from one beat to the next (keeps the choice steady)


def _snap(t: int, step: float) -> int:
    return round(round(t / step) * step)


def beat_grids(onsets: list[int], tpq: int, divisions: list[int]) -> dict[int, int]:
    """Pick the division count for each beat that has onsets (Viterbi over beats, see module doc)."""
    import numpy as np

    by_beat: dict[int, list[int]] = {}
    for t in onsets:
        # Assign onsets slightly before a beat to that beat.
        b = (t + tpq // 16) // tpq
        by_beat.setdefault(b, []).append(t)
    beats = sorted(by_beat)
    if not beats:
        return {}
    # cost[i, k]: timing error (in grid steps) of beat i's onsets on grid k, plus that grid's penalty
    cost = np.array(
        [
            [
                sum(abs(t - _snap(t, tpq / d)) for t in by_beat[b]) * d / tpq + TRIPLET_BIAS.get(d, 0.0)
                for d in divisions
            ]
            for b in beats
        ]
    )
    k = len(divisions)
    switch = GRID_SWITCH * (1 - np.eye(k))
    total = cost[0].copy()
    back = []
    for i in range(1, len(beats)):
        options = total[:, None] + switch
        prev = options.argmin(axis=0)
        back.append(prev)
        total = options[prev, np.arange(k)] + cost[i]
    path = [int(total.argmin())]
    for prev in reversed(back):
        path.append(int(prev[path[-1]]))
    path.reverse()
    return {b: divisions[g] for b, g in zip(beats, path, strict=True)}


def quantize_notes(notes: list[Note], tpq: int, level: str) -> list[Note]:
    if level == "off" or not notes:
        return [n.model_copy() for n in notes]
    divisions = GRIDS[level]
    grids = beat_grids([n.tick for n in notes], tpq, divisions)

    def snap(t: int) -> tuple[int, int]:
        b = (t + tpq // 16) // tpq
        div = grids.get(b, divisions[0])
        step = tpq / div
        return _snap(t, step), round(step)

    out: list[Note] = []
    for n in notes:
        start, step = snap(n.tick)
        end, _ = snap(n.tick + n.duration_ticks)
        out.append(n.model_copy(update={"tick": max(0, start), "duration_ticks": max(step, end - start)}))

    # Merge duplicates (same onset + pitch) and cut overlaps of repeated pitches.
    out.sort(key=lambda n: (n.midi, n.tick, -n.duration_ticks))
    merged: list[Note] = []
    for n in out:
        prev = merged[-1] if merged else None
        if prev and prev.midi == n.midi and prev.tick == n.tick:
            continue
        if prev and prev.midi == n.midi and prev.tick + prev.duration_ticks > n.tick:
            prev.duration_ticks = n.tick - prev.tick
        merged.append(n)
    merged.sort(key=lambda n: (n.tick, n.midi))
    return merged
