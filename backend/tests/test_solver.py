from conftest import make_notes

from tabiffy.models import Note
from tabiffy.solver import assign_fingers, load_config, solve_track
from tabiffy.tunings import STANDARD_GUITAR, tuning_midi

STD = tuning_midi(STANDARD_GUITAR)
CFG = load_config()


def solve(notes, **kw):
    kw.setdefault("standard_tuning", True)
    return solve_track(notes, STD, kw.pop("capo", 0), CFG, **kw)


def shape(res):
    """{string: (fret, finger)}"""
    return {n.string: (n.fret, n.finger) for n in res.notes}


def chord(midis, tick=0, dur=1920):
    return [(tick, dur, m) for m in midis]


def test_open_c_chord():
    res = solve(make_notes(chord([48, 52, 55, 60, 64])), chords_at={0: "C"})
    assert shape(res) == {5: (3, 3), 4: (2, 2), 3: (0, 0), 2: (1, 1), 1: (0, 0)}


def test_open_g_chord_is_open_position():
    res = solve(make_notes(chord([43, 47, 50, 55, 59, 67])), chords_at={0: "G"})
    frets = {s: f for s, (f, _) in shape(res).items()}
    assert frets == {6: 3, 5: 2, 4: 0, 3: 0, 2: 0, 1: 3}


def test_e_shape_barre_at_fret_5():
    # A major: A2 E3 A3 C#4 E4 A4
    res = solve(make_notes(chord([45, 52, 57, 61, 64, 69])))
    assert shape(res) == {6: (5, 1), 5: (7, 3), 4: (7, 4), 3: (6, 2), 2: (5, 1), 1: (5, 1)}
    assert all("barre" in n.flags for n in res.notes if n.fret == 5)


def test_f_barre_fingering():
    fr = assign_fingers([(6, 1), (5, 3), (4, 3), (3, 2), (2, 1), (1, 1)], 1)
    assert fr.barre and fr.feasible
    assert fr.fingers == [1, 3, 4, 2, 1, 1]


def test_a_shape_falls_back_to_packed_fingers():
    fr = assign_fingers([(5, 5), (4, 7), (3, 7), (2, 7), (1, 5)], 5)
    assert fr.feasible and fr.barre
    assert fr.fingers[0] == 1 and fr.fingers[4] == 1
    assert sorted(fr.fingers[1:4]) == [2, 3, 4]


def test_open_strings_get_finger_zero():
    fr = assign_fingers([(1, 0), (2, 1)], 1)
    assert fr.fingers == [0, 1]


def test_pentatonic_box_stays_at_fifth_position():
    # A minor pentatonic, box 1 (fret 5), as 16th notes up and down
    up = [45, 48, 50, 52, 55, 57, 60, 62, 64, 67, 69, 72]
    line = up + up[-2::-1]
    res = solve(make_notes([(i * 240, 240, m) for i, m in enumerate(line)]))
    assert all(5 <= n.fret <= 8 for n in res.notes)
    for n in res.notes:
        assert n.finger == n.fret - 5 + 1 if n.fret != 8 else n.finger == 4
        assert n.finger in (1, 3, 4)


def test_every_note_is_playable_on_its_string():
    import random

    rng = random.Random(1)
    notes = make_notes([(i * 240, 240, rng.randint(40, 84)) for i in range(64)])
    res = solve(notes)
    open_by_string = {6 - i: m for i, m in enumerate(STD)}
    assert len(res.notes) == 64
    for n in res.notes:
        assert open_by_string[n.string] + n.fret == n.midi


def test_one_note_per_string_and_reduction_of_dense_slices():
    # 8 simultaneous notes on a 6-string guitar -> reduced, keeping bass + melody
    midis = [40, 45, 52, 55, 59, 64, 67, 76]
    res = solve(make_notes(chord(midis)))
    strings = [n.string for n in res.notes]
    assert len(strings) == len(set(strings)) <= 6
    kept = {n.midi for n in res.notes}
    assert 40 in kept and 76 in kept
    assert len(res.dropped) == 8 - len(res.notes)


def test_simplify_chords_limits_to_four_notes():
    res = solve(make_notes(chord([43, 47, 50, 55, 59, 67])), max_notes_per_slice=4)
    assert len(res.notes) == 4


def test_locked_note_keeps_its_position():
    notes = make_notes([(0, 480, 64), (480, 480, 67)])
    notes[0] = Note(id="n0", tick=0, duration_ticks=480, midi=64, string=2, fret=5, user_edited=True)
    res = solve(notes)
    locked = next(n for n in res.notes if n.id == "n0")
    assert (locked.string, locked.fret) == (2, 5)


def test_capo_frets_are_relative_to_capo():
    # D3 (50) with capo 2 on the D string -> fret 0
    res = solve(make_notes([(0, 480, 50)]), capo=2)
    n = res.notes[0]
    assert n.fret + STD[6 - n.string] + 2 == 50


def test_bass_tuning():
    from tabiffy.tunings import STANDARD_BASS

    res = solve_track(make_notes([(0, 480, 28), (480, 480, 33), (960, 480, 38)]), tuning_midi(STANDARD_BASS), 0, CFG)
    assert [(n.string, n.fret) for n in res.notes] == [(4, 0), (3, 0), (2, 0)]
