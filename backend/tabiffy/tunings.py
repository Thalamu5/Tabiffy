"""Tuning presets (SPEC 6.4). Lists are low string -> high string."""

from __future__ import annotations

from .pitch import name_to_midi


def _t(label: str, instrument: str, notes: str, family: str, prior: float) -> dict:
    """family: how the tuning relates to standard (shown in the UI); prior: how unusual it is, used as a
    small tie-breaker when suggesting tunings (0 = most common)."""
    n = notes.split()
    return {"label": label, "instrument": instrument, "notes": n, "strings": len(n), "family": family, "prior": prior}


TUNINGS: dict[str, dict] = {
    # 6-string guitar
    "standard": _t("Standard (E A D G B E)", "guitar", "E2 A2 D3 G3 B3 E4", "standard", 0.0),
    "eb-standard": _t("Eb Standard", "guitar", "Eb2 Ab2 Db3 Gb3 Bb3 Eb4", "standard", 0.1),
    "d-standard": _t("D Standard", "guitar", "D2 G2 C3 F3 A3 D4", "standard", 0.12),
    "c-standard": _t("C Standard", "guitar", "C2 F2 Bb2 Eb3 G3 C4", "standard", 0.15),
    "b-standard": _t("B Standard", "guitar", "B1 E2 A2 D3 F#3 B3", "standard", 0.2),
    "drop-d": _t("Drop D", "guitar", "D2 A2 D3 G3 B3 E4", "drop", 0.05),
    "drop-c-sharp": _t("Drop C#", "guitar", "C#2 G#2 C#3 F#3 A#3 D#4", "drop", 0.15),
    "drop-c": _t("Drop C", "guitar", "C2 G2 C3 F3 A3 D4", "drop", 0.12),
    "drop-b": _t("Drop B", "guitar", "B1 F#2 B2 E3 G#3 C#4", "drop", 0.18),
    "drop-a": _t("Drop A", "guitar", "A1 E2 A2 D3 F#3 B3", "drop", 0.22),
    "dadgad": _t("DADGAD", "guitar", "D2 A2 D3 G3 A3 D4", "open", 0.3),
    "open-g": _t("Open G", "guitar", "D2 G2 D3 G3 B3 D4", "open", 0.3),
    "open-d": _t("Open D", "guitar", "D2 A2 D3 F#3 A3 D4", "open", 0.3),
    "open-e": _t("Open E", "guitar", "E2 B2 E3 G#3 B3 E4", "open", 0.35),
    # 7-string guitar
    "7-string-b": _t("7-string B Standard (B E A D G B E)", "guitar", "B1 E2 A2 D3 G3 B3 E4", "standard", 0.15),
    "7-string-a": _t("7-string A Standard", "guitar", "A1 D2 G2 C3 F3 A3 D4", "standard", 0.25),
    "7-string-drop-a": _t("7-string Drop A", "guitar", "A1 E2 A2 D3 G3 B3 E4", "drop", 0.2),
    "7-string-drop-g": _t("7-string Drop G", "guitar", "G1 D2 G2 C3 F3 A3 D4", "drop", 0.28),
    # 8-string guitar
    "8-string-f-sharp": _t(
        "8-string F# Standard (F# B E A D G B E)", "guitar", "F#1 B1 E2 A2 D3 G3 B3 E4", "standard", 0.25
    ),
    "8-string-drop-e": _t("8-string Drop E", "guitar", "E1 B1 E2 A2 D3 G3 B3 E4", "drop", 0.3),
    # bass (more bass options come with the bass work)
    "bass-4": _t("Bass 4-string (E A D G)", "bass", "E1 A1 D2 G2", "standard", 0.0),
    "bass-5": _t("Bass 5-string (B E A D G)", "bass", "B0 E1 A1 D2 G2", "standard", 0.1),
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
