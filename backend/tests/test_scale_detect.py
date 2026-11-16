"""Key and scale detection on short phrases whose scale is known."""

import pytest
from conftest import make_notes

from tabiffy.chords import label_chords
from tabiffy.pitch import name_to_midi as m
from tabiffy.scale_detect import analyze_key

Q = 960


def phrase(tonic_bass: str, melody: str, chord_tones: str = ""):
    """A bass drone on the tonic, a melody in 8ths and an optional sustained chord, repeated 4 times."""
    spec, t = [], 0
    mel = melody.split()
    for _ in range(4):
        spec.append((t, len(mel) * Q // 2, m(tonic_bass)))
        for c in chord_tones.split():
            spec.append((t, len(mel) * Q // 2, m(c)))
        for i, n in enumerate(mel):
            spec.append((t + i * Q // 2, Q // 2, m(n)))
        t += len(mel) * Q // 2 + Q  # a beat of rest ends each phrase
    return make_notes(spec)


def analyze(notes):
    return analyze_key(notes, label_chords(notes, Q), Q)


@pytest.mark.parametrize(
    ("bass", "melody", "chord", "label"),
    [
        ("C2", "C4 D4 E4 F4 G4 A4 B4 C5 G4 E4 C4", "E3 G3", "C major"),
        ("A1", "A3 B3 C4 D4 E4 F4 G4 A4 E4 C4 A3", "C3 E3", "A natural minor"),
        ("A1", "A3 B3 C4 D4 E4 F4 G#4 A4 G#4 E4 A3", "C3 E3", "A harmonic minor"),
        ("E2", "E3 F3 G#3 A3 B3 C4 D4 E4 F4 E4 G#3 E3", "G#2 B2", "E Phrygian Dominant"),
        ("D2", "D3 E3 F3 G3 A3 B3 C4 D4 B3 A3 F3 D3", "F2 A2", "D Dorian"),
        ("A1", "A3 C4 D4 E4 G4 A4 G4 E4 D4 C4 A3", "C3 E3", "A minor pentatonic"),
    ],
)
def test_known_scales(bass, melody, chord, label):
    ka = analyze(phrase(bass, melody, chord))
    assert ka is not None and ka.scale.label == label


def test_spelling_uses_each_letter_once():
    ka = analyze(phrase("F#1", "F#3 G3 A#3 B3 C#4 D4 E4 F#4 E4 A#3 F#3", "A#2 C#3"))
    assert ka.scale.label == "F# Phrygian Dominant"
    assert ka.scale.notes == ["F#", "G", "A#", "B", "C#", "D", "E"]
    assert ka.key == "F# major"  # its 3rd is major


def test_reasons_explain_what_makes_the_scale():
    ka = analyze(phrase("E2", "E3 F3 G#3 A3 B3 C4 D4 E4 F4 E4 G#3 E3", "G#2 B2"))
    text = " ".join(ka.reasons)
    assert text.startswith("E feels like home")
    assert "F (the flat 2nd)" in text
    assert len(ka.alternatives) == 2 and all(a.relative >= 0 for a in ka.alternatives)
    assert sum(ka.histogram) == pytest.approx(1.0, abs=1e-3)


def test_no_notes_no_analysis():
    assert analyze_key([], [], Q) is None
