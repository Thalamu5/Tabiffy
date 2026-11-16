"""Slides, hammer-ons and pull-offs: detection from audio clues, and keeping them on one string."""

import numpy as np
import pytest
from audio_synth import legato_line, write
from conftest import make_notes

from tabiffy.audio.legato import find_links
from tabiffy.audio.transcribe import RawNote
from tabiffy.solver import load_config, solve_track
from tabiffy.tunings import STANDARD_GUITAR, tuning_midi


def raw(start, end, pitch, attack=1.0, glide_in=0.0):
    return RawNote(start, end, pitch, 0.6, attack, glide_in)


def test_hammer_pull_and_slide_from_clues():
    notes = [
        raw(0.0, 0.5, 60),  # picked
        raw(0.5, 1.0, 62, attack=0.1),  # no attack, pitch jumps up: hammer-on
        raw(1.0, 1.5, 60, attack=0.1),  # no attack, jumps down: pull-off
        raw(1.5, 2.0, 60),  # picked...
        raw(2.0, 2.5, 65, attack=0.1, glide_in=-4.5),  # ...pitch arrives smoothly from below: slide
        raw(2.5, 3.0, 67),  # picked: no technique
    ]
    found = {(lk.first, lk.second): (lk.technique, lk.sure) for lk in find_links(notes)}
    assert found == {(0, 1): ("hammer", True), (1, 2): ("pull", True), (3, 4): ("slide", True)}


def test_chord_notes_and_picked_notes_are_not_linked():
    chord = [raw(0.0, 1.0, 48), raw(0.01, 1.0, 52), raw(0.02, 1.0, 55)]
    picked = [raw(1.0, 1.5, 57, attack=0.9)]
    assert find_links(chord + picked) == []


def test_weak_evidence_is_only_a_suggestion():
    # Attack is only somewhat weaker than the first note's: we suggest, we don't claim.
    links = find_links([raw(0.0, 0.5, 60, attack=0.9), raw(0.5, 1.0, 62, attack=0.4)])
    assert [(lk.technique, lk.sure) for lk in links] == [("hammer", False)]


def test_solver_keeps_a_hammer_on_one_string():
    # D4 -> E4: normally D on the B string and E on the open high E. Linked, both go on the B string.
    notes = make_notes([(0, 480, 62), (480, 480, 64)])
    plain = solve_track([n.model_copy() for n in notes], tuning_midi(STANDARD_GUITAR), 0, load_config())
    assert plain.notes[0].string != plain.notes[1].string
    notes[0].techniques, notes[0].legato_to = ["hammer"], notes[1].id
    res = solve_track(notes, tuning_midi(STANDARD_GUITAR), 0, load_config()).notes
    a, b = sorted(res, key=lambda n: n.tick)
    assert a.string == b.string and b.fret > a.fret and a.techniques == ["hammer"]


def test_impossible_technique_is_dropped():
    # Two notes at the same moment can't be a hammer-on: the link is removed after solving.
    notes = make_notes([(0, 480, 60), (0, 480, 64)])
    notes[0].techniques, notes[0].legato_to = ["hammer"], notes[1].id
    res = solve_track(notes, tuning_midi(STANDARD_GUITAR), 0, load_config()).notes
    assert all(not n.techniques and n.legato_to is None for n in res)


@pytest.fixture(scope="module")
def legato_recording(tmp_path_factory):
    pytest.importorskip("basic_pitch")
    line = legato_line(
        [
            (57, 0.5, "pick"), (59, 0.5, "hammer"), (57, 0.5, "pull"),
            (55, 0.6, "pick"), (60, 0.6, "slide"),
            (64, 0.5, "pick"), (62, 0.5, "pick"),
        ]
    )  # fmt: skip
    return write(tmp_path_factory.mktemp("legato") / "line.wav", np.concatenate([line, np.zeros(22050)]))


def test_detects_techniques_in_a_recording(legato_recording):
    from tabiffy.audio.transcribe import transcribe

    notes = transcribe(legato_recording, "guitar")
    techniques = {(notes[lk.first].pitch, notes[lk.second].pitch): lk.technique for lk in find_links(notes)}
    assert techniques.get((57, 59)) == "hammer"
    assert techniques.get((59, 57)) == "pull"
    assert techniques.get((55, 60)) == "slide"
    assert (64, 62) not in techniques  # two picked notes
