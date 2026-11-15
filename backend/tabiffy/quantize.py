"""Stage 8: snap onsets/durations to a rhythmic grid.

The grid is chosen per quarter note: with triplets enabled, each beat uses either
the straight 1/16 grid or the 1/8-triplet grid, whichever fits that beat's onsets
best (straight wins ties). Keeping one grid per beat means the result can always be
written with standard note values.
"""

from __future__ import annotations

from .models import Note

GRIDS = {
    "1/8": [2],  # divisions per quarter note
    "1/16": [4],
    "1/32": [8],
    "1/16+triplets": [4, 3],
}
TRIPLET_BIAS = 0.02  # fraction of a quarter, per note, added to the triplet grid's error


def _snap(t: int, step: float) -> int:
    return round(round(t / step) * step)


def beat_grids(onsets: list[int], tpq: int, divisions: list[int]) -> dict[int, int]:
    """Pick the division count to use for each beat that contains onsets."""
    by_beat: dict[int, list[int]] = {}
    for t in onsets:
        # Assign onsets slightly before a beat to that beat.
        b = (t + tpq // 16) // tpq
        by_beat.setdefault(b, []).append(t)
    chosen: dict[int, int] = {}
    for b, ts in by_beat.items():
        best, best_err = divisions[0], float("inf")
        for i, div in enumerate(divisions):
            step = tpq / div
            err = sum(abs(t - _snap(t, step)) for t in ts) / tpq
            if div % 3 == 0:
                err += TRIPLET_BIAS * len(ts)
            if err < best_err - 1e-9 or (i == 0 and err <= best_err):
                best, best_err = div, err
        chosen[b] = best
    return chosen


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
