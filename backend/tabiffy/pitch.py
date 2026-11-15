"""Pitch helpers: note names <-> MIDI numbers, chord-symbol transposition."""

from __future__ import annotations

import re

NOTE_NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTE_NAMES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
_PC = {
    "C": 0,
    "B#": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "FB": 4,
    "E#": 5,
    "F": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
    "CB": 11,
}
_NAME_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d+)$")


def name_to_midi(name: str) -> int:
    """'E2' -> 40, 'C#4' -> 61, 'Eb3' -> 51."""
    m = _NAME_RE.match(name.strip())
    if not m:
        raise ValueError(f"Not a note name: {name!r}")
    letter, acc, octave = m.groups()
    pc = _PC[(letter + acc).upper()]
    return pc + (int(octave) + 1) * 12


def midi_to_name(midi: int, flats: bool = False) -> str:
    names = NOTE_NAMES_FLAT if flats else NOTE_NAMES_SHARP
    return f"{names[midi % 12]}{midi // 12 - 1}"


def pc_name(pc: int, flats: bool = False) -> str:
    return (NOTE_NAMES_FLAT if flats else NOTE_NAMES_SHARP)[pc % 12]


def parse_pc(name: str) -> int:
    return _PC[name.upper()]


_CHORD_RE = re.compile(r"^([A-G][#b]?)(.*?)(?:/([A-G][#b]?))?$")


def transpose_chord_symbol(symbol: str, semitones: int) -> str:
    """'G7' + 2 -> 'A7'; 'C/E' - 2 -> 'A#/D' (sharps unless the input used flats)."""
    m = _CHORD_RE.match(symbol)
    if not m:
        return symbol
    root, quality, bass = m.groups()
    flats = "b" in root
    out = pc_name(parse_pc(root) + semitones, flats) + quality
    if bass:
        out += "/" + pc_name(parse_pc(bass) + semitones, flats)
    return out
