"""Tuning presets (SPEC 6.4). Lists are low string -> high string."""

from __future__ import annotations

from .pitch import name_to_midi

TUNINGS: dict[str, dict] = {
    "standard": {"label": "Standard (EADGBE)", "instrument": "guitar", "notes": ["E2", "A2", "D3", "G3", "B3", "E4"]},
    "drop-d": {"label": "Drop D", "instrument": "guitar", "notes": ["D2", "A2", "D3", "G3", "B3", "E4"]},
    "d-standard": {"label": "D Standard", "instrument": "guitar", "notes": ["D2", "G2", "C3", "F3", "A3", "D4"]},
    "eb-standard": {
        "label": "Eb Standard",
        "instrument": "guitar",
        "notes": ["Eb2", "Ab2", "Db3", "Gb3", "Bb3", "Eb4"],
    },
    "dadgad": {"label": "DADGAD", "instrument": "guitar", "notes": ["D2", "A2", "D3", "G3", "A3", "D4"]},
    "open-g": {"label": "Open G", "instrument": "guitar", "notes": ["D2", "G2", "D3", "G3", "B3", "D4"]},
    "open-d": {"label": "Open D", "instrument": "guitar", "notes": ["D2", "A2", "D3", "F#3", "A3", "D4"]},
    "open-e": {"label": "Open E", "instrument": "guitar", "notes": ["E2", "B2", "E3", "G#3", "B3", "E4"]},
    "7-string-b": {
        "label": "7-string B Standard",
        "instrument": "guitar",
        "notes": ["B1", "E2", "A2", "D3", "G3", "B3", "E4"],
    },
    "bass-4": {"label": "Bass 4-string (EADG)", "instrument": "bass", "notes": ["E1", "A1", "D2", "G2"]},
    "bass-5": {"label": "Bass 5-string (BEADG)", "instrument": "bass", "notes": ["B0", "E1", "A1", "D2", "G2"]},
}

STANDARD_GUITAR = TUNINGS["standard"]["notes"]
STANDARD_BASS = TUNINGS["bass-4"]["notes"]

# Piano range A0-C8.
PIANO_RANGE = (21, 108)


def tuning_midi(tuning: list[str]) -> list[int]:
    return [name_to_midi(n) for n in tuning]


def is_standard_guitar(tuning: list[str]) -> bool:
    return tuning_midi(tuning) == tuning_midi(STANDARD_GUITAR)


def default_tuning(target: str) -> list[str]:
    return list(STANDARD_BASS if target == "bass" else STANDARD_GUITAR)
