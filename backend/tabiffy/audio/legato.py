"""Find slides, hammer-ons and pull-offs in transcribed audio.

A legato note follows the previous one with no new pick attack. If the pitch glides between them it's
a slide; if it jumps it's a hammer-on (up) or pull-off (down). Weak evidence gives a *suggested*
technique, which the tab shows in a different color so the player can judge it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .transcribe import RawNote

MAX_GAP = 0.04  # seconds of silence allowed between the two notes
MAX_OVERLAP = 0.04  # seconds the first note may still ring after the second starts
CHORD_WINDOW = 0.03  # notes starting this close together are a chord, where legato isn't detected
# Attack is relative to a typical picked note (1.0). Hammer-ons still "click" at roughly half a pick.
WEAK_ATTACK = 0.6  # below this counts as "not picked"
SURE_ATTACK = 0.25  # below this we're confident there was no pick attack
RELATIVE_ATTACK = 0.6  # ...or the second onset is this much weaker than the first
GLIDE = 0.6  # semitones of smooth pitch movement into the second note that indicate a slide
MAX_SLIDE_GAP = 0.15  # a slide's in-between pitches are often left out of both notes, leaving a gap
MAX_INTERVAL = 24  # slides and tapping pull-offs travel far; anything wider is treated as a new phrase
MAX_LEGATO_INTERVAL = 5  # widest normal hammer-on/pull-off (wider ones are suggestions only)


@dataclass
class Link:
    first: int  # index of the note the technique starts on
    second: int  # index of the note it leads into
    technique: str  # "slide", "hammer" or "pull"
    sure: bool


def find_links(notes: list[RawNote]) -> list[Link]:
    """Pair each note with the note it flows into, if the second note has no real pick attack."""
    order = sorted(range(len(notes)), key=lambda i: notes[i].start)
    starts = [notes[i].start for i in order]
    # Only single-note lines: a note starting together with another one is part of a chord.
    in_chord = {
        order[k]
        for k in range(len(order))
        if (k > 0 and starts[k] - starts[k - 1] < CHORD_WINDOW)
        or (k + 1 < len(order) and starts[k + 1] - starts[k] < CHORD_WINDOW)
    }
    links: list[Link] = []
    used_first: set[int] = set()
    for pos, b in enumerate(order):
        nb = notes[b]
        if b in in_chord:
            continue
        best: tuple[float, int] | None = None
        # Look back a few notes for one that ends right where this one starts.
        for a in order[max(0, pos - 6) : pos]:
            na = notes[a]
            interval = abs(nb.pitch - na.pitch)
            if a in used_first or a in in_chord or not 1 <= interval <= MAX_INTERVAL:
                continue
            gap = MAX_SLIDE_GAP if nb.glide_in else MAX_GAP
            if not (nb.start - gap <= na.end <= nb.start + MAX_OVERLAP) or nb.start - na.start < 0.03:
                continue
            closeness = abs(na.end - nb.start) + 0.01 * interval  # prefer the nearest, closest-pitched note
            if best is None or closeness < best[0]:
                best = (closeness, a)
        if best is None:
            continue
        a = best[1]
        link = classify(notes[a], nb)
        if link:
            links.append(Link(a, b, *link))
            used_first.add(a)
    return links


def classify(a: RawNote, b: RawNote) -> tuple[str, bool] | None:
    """Decide the technique between two connected notes, or None if `b` was simply picked."""
    up = 1 if b.pitch > a.pitch else -1
    legato = b.attack < WEAK_ATTACK or b.attack < RELATIVE_ATTACK * a.attack
    # Glide: the second note's pitch arrived smoothly from the first note's direction.
    glide = -up * b.glide_in
    if glide >= GLIDE:
        return "slide", legato and glide >= 1.0
    if not legato:
        return None
    interval = abs(b.pitch - a.pitch)
    sure = b.attack < SURE_ATTACK and interval <= MAX_LEGATO_INTERVAL
    return ("hammer" if up > 0 else "pull"), sure
