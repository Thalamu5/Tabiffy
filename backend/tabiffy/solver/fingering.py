"""Assign fingers 1-4 for a chosen chord shape and hand position (the fret under the index finger).
Tries in order: one finger per fret, fingers packed tightly, an index-finger barre, then a clipped
fallback flagged as hard."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FingerResult:
    fingers: list[int]  # parallel to the input positions
    barre: bool = False
    stretch: list[bool] = field(default_factory=list)
    feasible: bool = True


def _sequential(items: list[tuple[int, int, int]], position: int, start: int, use_offset: bool) -> dict | None:
    """items: (index, string, fret) sorted by fret asc then string desc (low strings first)."""
    out: dict[int, int] = {}
    prev = start - 1
    for idx, _s, fret in items:
        want = fret - position + 1 if use_offset else prev + 1
        f = max(want, prev + 1, 1)
        if f > 4:
            return None
        out[idx] = f
        prev = f
    return out


def assign_fingers(positions: list[tuple[int, int]], position: int | None) -> FingerResult:
    """positions: list of (string, fret); string 1 = highest string."""
    fingers = [0] * len(positions)
    stretch = [False] * len(positions)
    fretted = [(i, s, f) for i, (s, f) in enumerate(positions) if f > 0]
    if not fretted:
        return FingerResult(fingers, stretch=stretch)
    min_fret = min(f for _, _, f in fretted)
    pos = position if position is not None else min_fret
    pos = min(pos, min_fret)
    fretted.sort(key=lambda t: (t[2], -t[1]))

    def finish(mapping: dict[int, int], barre: bool) -> FingerResult:
        for i, f in mapping.items():
            fingers[i] = f
            stretch[i] = positions[i][1] - pos >= 4
        return FingerResult(fingers, barre=barre, stretch=stretch)

    for use_offset in (True, False):
        m = _sequential(fretted, pos, 1, use_offset)
        if m is not None:
            return finish(m, False)

    # Index barre on the lowest fret.
    barre_notes = [t for t in fretted if t[2] == min_fret]
    if len(barre_notes) >= 2:
        lo = min(s for _, s, _ in barre_notes)
        hi = max(s for _, s, _ in barre_notes)
        open_inside = any(f == 0 and lo <= s <= hi for s, f in positions)
        if not open_inside:
            rest = [t for t in fretted if t[2] != min_fret]
            for use_offset in (True, False):
                m = _sequential(rest, min_fret, 2, use_offset)
                if m is not None:
                    m.update({i: 1 for i, _, _ in barre_notes})
                    return finish(m, True)

    clipped = {i: max(1, min(4, f - pos + 1)) for i, _, f in fretted}
    res = finish(clipped, False)
    res.feasible = False
    return res
