"""Stage 6: instrument mapping & transposition (SPEC 5.3)."""

from __future__ import annotations

from .models import Note
from .tunings import PIANO_RANGE

PIANO_SPLIT = 60  # middle C: notes below go to the left hand


def instrument_range(target: str, open_midi: list[int], capo: int, max_fret: int) -> tuple[int, int]:
    if target == "piano":
        return PIANO_RANGE
    return min(open_midi) + capo, max(open_midi) + capo + max_fret


COMFORT_FRETS = 12


def comfort_range(target: str, open_midi: list[int], capo: int) -> tuple[int, int]:
    """Where music moved from another instrument should preferably land."""
    if target == "piano":
        return 36, 84  # C2-C6
    return min(open_midi) + capo, max(open_midi) + capo + COMFORT_FRETS


def split_phrases(notes: list[Note], gap_ticks: int) -> list[list[Note]]:
    """Split into phrases separated by at least `gap_ticks` of silence."""
    phrases: list[list[Note]] = []
    end = -1
    for n in sorted(notes, key=lambda n: n.tick):
        if not phrases or n.tick - end >= gap_ticks:
            phrases.append([])
        phrases[-1].append(n)
        end = max(end, n.tick + n.duration_ticks)
    return phrases


def best_octave_shift(midis: list[int], lo: int, hi: int, comfort: tuple[int, int] | None = None) -> int:
    """Octave shift (in octaves) that keeps the most notes in [lo, hi].

    Ties go to the shift with the most notes in the `comfort` range (e.g. frets 0-12),
    then to the smallest shift. Without `comfort`, pitches are kept unless they don't fit.
    """
    best, best_key = 0, None
    for k in range(-5, 6):
        inside = sum(1 for m in midis if lo <= m + 12 * k <= hi)
        cozy = sum(1 for m in midis if comfort[0] <= m + 12 * k <= comfort[1]) if comfort else 0
        key = (inside, cozy, -abs(k), k)
        if best_key is None or key > best_key:
            best, best_key = k, key
    return best


def map_to_range(
    notes: list[Note], lo: int, hi: int, transpose: int, phrase_gap_ticks: int, comfort: tuple[int, int] | None = None
) -> list[Note]:
    """Transpose, then shift whole phrases by octaves into range; fold & flag leftovers."""
    out: list[Note] = []
    for phrase in split_phrases(notes, phrase_gap_ticks):
        shifted = [n.model_copy(deep=True) for n in phrase]
        for n in shifted:
            if not n.user_edited:
                n.midi += transpose
        free = [n for n in shifted if not n.user_edited]
        k = best_octave_shift([n.midi for n in free], lo, hi, comfort)
        for n in free:
            n.midi += 12 * k
            n.flags = [f for f in n.flags if f != "outOfRange"]
            if not lo <= n.midi <= hi:
                while n.midi < lo:
                    n.midi += 12
                while n.midi > hi:
                    n.midi -= 12
                n.flags.append("outOfRange")
        out.extend(shifted)
    out.sort(key=lambda n: (n.tick, n.midi))
    return out


def assign_hands(notes: list[Note], split: int = PIANO_SPLIT) -> list[Note]:
    """v0.1 piano: left/right hand by a split point; fingering (1-5) comes in v1.1."""
    out = []
    for n in notes:
        c = n.model_copy(deep=True)
        c.string = c.fret = None
        if not (c.user_edited and c.hand):
            c.hand = "L" if c.midi < split else "R"
        if not c.user_edited:
            c.finger = None
        out.append(c)
    return out
