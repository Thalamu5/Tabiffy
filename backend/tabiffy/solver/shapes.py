"""Common open ("cowboy") chord shapes in standard tuning, low E -> high E.

None = string not played. Used for a small cost bonus when a slice's chord label
matches (SPEC 5.1 "Preferences").
"""

from __future__ import annotations

X = None
OPEN_SHAPES: dict[str, list[int | None]] = {
    "C": [X, 3, 2, 0, 1, 0],
    "A": [X, 0, 2, 2, 2, 0],
    "G": [3, 2, 0, 0, 0, 3],
    "E": [0, 2, 2, 1, 0, 0],
    "D": [X, X, 0, 2, 3, 2],
    "Am": [X, 0, 2, 2, 1, 0],
    "Em": [0, 2, 2, 0, 0, 0],
    "Dm": [X, X, 0, 2, 3, 1],
    "E7": [0, 2, 0, 1, 0, 0],
    "A7": [X, 0, 2, 0, 2, 0],
    "D7": [X, X, 0, 2, 1, 2],
    "G7": [3, 2, 0, 0, 0, 1],
    "C7": [X, 3, 2, 3, 1, 0],
    "B7": [X, 2, 1, 2, 0, 2],
    "Fmaj7": [X, X, 3, 2, 1, 0],
    "Cmaj7": [X, 3, 2, 0, 0, 0],
    "Amaj7": [X, 0, 2, 1, 2, 0],
    "Am7": [X, 0, 2, 0, 1, 0],
    "Em7": [0, 2, 0, 0, 0, 0],
    "Dmaj7": [X, X, 0, 2, 2, 2],
    "Asus2": [X, 0, 2, 2, 0, 0],
    "Asus4": [X, 0, 2, 2, 3, 0],
    "Dsus2": [X, X, 0, 2, 3, 0],
    "Dsus4": [X, X, 0, 2, 3, 3],
    "Esus4": [0, 2, 2, 2, 0, 0],
    "F": [1, 3, 3, 2, 1, 1],
    "Bm": [X, 2, 4, 4, 3, 2],
    "G/B": [X, 2, 0, 0, 0, 3],
    "C/G": [3, 3, 2, 0, 1, 0],
    "D/F#": [2, X, 0, 2, 3, 2],
    "E5": [0, 2, 2, X, X, X],
    "A5": [X, 0, 2, 2, X, X],
    "D5": [X, X, 0, 2, 3, X],
}

# Enharmonic spellings the chord labeler may produce
_ALIASES = {
    "F#": "Gb",
    "Gb": "F#",
    "C#": "Db",
    "Db": "C#",
    "G#": "Ab",
    "Ab": "G#",
    "D#": "Eb",
    "Eb": "D#",
    "A#": "Bb",
    "Bb": "A#",
}


def shape_positions(symbol: str, n_strings: int = 6) -> set[tuple[int, int]] | None:
    """(string, fret) pairs of the open shape for `symbol`, string 1 = high E."""
    shape = OPEN_SHAPES.get(symbol)
    if shape is None and len(symbol) >= 2 and symbol[:2] in _ALIASES:
        shape = OPEN_SHAPES.get(_ALIASES[symbol[:2]] + symbol[2:])
    if shape is None or n_strings != 6:
        return None
    return {(6 - i, f) for i, f in enumerate(shape) if f is not None}
