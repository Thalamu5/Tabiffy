from conftest import make_notes

from tabiffy.chords import label_chords
from tabiffy.key_detect import detect_key
from tabiffy.mapping import assign_hands, best_octave_shift, map_to_range
from tabiffy.pitch import midi_to_name, name_to_midi, transpose_chord_symbol
from tabiffy.quantize import quantize_notes

TPQ = 960
BAR = 4 * TPQ


def bars(*chords):
    spec = []
    for i, midis in enumerate(chords):
        spec += [(i * BAR, BAR, m) for m in midis]
    return make_notes(spec)


# --- chord labeler -----------------------------------------------------------
def test_chord_templates():
    notes = bars([48, 52, 55], [45, 48, 52], [43, 47, 50, 53], [50, 53, 57, 60], [40, 47], [50, 55, 57])
    syms = [c.symbol for c in label_chords(notes, TPQ)]
    assert syms == ["C", "Am", "G7", "Dm7", "E5", "Dsus4"]


def test_slash_chord():
    notes = bars([40, 48, 55, 60])  # C over E bass
    assert [c.symbol for c in label_chords(notes, TPQ)] == ["C/E"]


def test_chord_labels_do_not_flicker():
    # a passing note for one 8th shouldn't create a new chord
    notes = make_notes([(0, 2 * BAR, 48), (0, 2 * BAR, 52), (0, 2 * BAR, 55), (BAR, 480, 62)])
    labels = label_chords(notes, TPQ)
    assert [c.symbol for c in labels] == ["C"]
    assert labels[0].duration_ticks == 2 * BAR


def test_one_beat_chords_fold_into_the_previous_chord():
    # Am for a bar, then one beat of F (a passing harmony), then Am again: reads as a single Am.
    am, f = [45, 52, 57, 60], [41, 48, 53, 57]
    spec = [(0, BAR, m) for m in am] + [(BAR, TPQ, m) for m in f] + [(BAR + TPQ, 3 * TPQ, m) for m in am]
    labels = label_chords(make_notes(spec), TPQ)
    assert [c.symbol for c in labels] == ["Am"]
    assert labels[0].duration_ticks == 2 * BAR


def test_key_detection():
    c_major = make_notes([(i * 480, 480, m) for i, m in enumerate([60, 62, 64, 65, 67, 69, 71, 72, 67, 64, 60])])
    assert detect_key(c_major) == "C major"


# --- quantizer ---------------------------------------------------------------
def test_quantize_snaps_to_sixteenths():
    notes = make_notes([(5, 470, 60), (250, 230, 62), (712, 260, 64)])
    q = quantize_notes(notes, TPQ, "1/16")
    assert [(n.tick, n.duration_ticks) for n in q] == [(0, 480), (240, 240), (720, 240)]


def test_quantize_triplets_only_where_they_fit():
    trip = make_notes([(0, 320, 60), (322, 318, 62), (641, 319, 64), (960, 240, 65), (1200, 240, 67)])
    q = quantize_notes(trip, TPQ, "1/16+triplets")
    assert [n.tick for n in q] == [0, 320, 640, 960, 1200]


def test_quantize_sixteenth_triplets():
    # Six notes per beat, played a little loosely (as in fast tapping or legato runs).
    jitter = [0, 12, -10, 8, -6, 14, 3, -12, 9, -4, 11, -8]
    sext = make_notes([(i * 160 + j, 150, 60 + i % 3) for i, j in enumerate(jitter)])
    q = quantize_notes(sext, TPQ, "1/16+triplets")
    assert [n.tick for n in q] == [i * 160 for i in range(12)]


def test_loose_straight_sixteenths_stay_straight():
    # Straight 16ths with up to ~1/25 of a beat of timing slop must not turn into triplets.
    jitter = [0, 30, -25, 35, 20, -30, 25, -35, 10, 38, -20, 28, -15, 33, -38, 18]
    notes = make_notes([(i * 240 + j, 220, 64) for i, j in enumerate(jitter)])
    q = quantize_notes(notes, TPQ, "1/16+triplets")
    assert [n.tick for n in q] == [i * 240 for i in range(16)]


def test_quantize_off_is_identity_and_merges_nothing():
    notes = make_notes([(7, 100, 60)])
    assert quantize_notes(notes, TPQ, "off")[0].tick == 7


def test_quantize_merges_duplicates():
    notes = make_notes([(0, 480, 60), (10, 480, 60)])
    assert len(quantize_notes(notes, TPQ, "1/16")) == 1


# --- mapping -------------------------------------------------------------------
def test_octave_shift_keeps_most_notes():
    assert best_octave_shift([91, 93, 95], 40, 86) == -1
    assert best_octave_shift([50, 60], 40, 86) == 0
    assert best_octave_shift([91, 93, 95], 40, 86, comfort=(40, 76)) == -2


def test_map_to_range_shifts_whole_phrase_and_flags_leftovers():
    notes = make_notes([(0, 480, 30), (480, 480, 52), (960, 480, 100)])
    out = map_to_range(notes, 40, 86, 0, phrase_gap_ticks=BAR)
    # one phrase: shifting by an octave can't fit both 30 and 100 -> fold + flag
    assert all(40 <= n.midi <= 86 for n in out)
    assert sum("outOfRange" in n.flags for n in out) >= 1
    # the phrase moves up an octave as a whole (2 of 3 notes fit), so 52 -> 64
    assert out[1].midi == 64


def test_transpose():
    out = map_to_range(make_notes([(0, 480, 60)]), 40, 86, 2, phrase_gap_ticks=BAR)
    assert out[0].midi == 62


def test_piano_hands():
    out = assign_hands(make_notes([(0, 480, 48), (0, 480, 72)]))
    assert [n.hand for n in out] == ["L", "R"]


def test_pitch_names():
    assert name_to_midi("E2") == 40 and name_to_midi("Eb4") == 63 and midi_to_name(61) == "C#4"
    assert transpose_chord_symbol("G7", 2) == "A7"
    assert transpose_chord_symbol("C/E", -2) == "A#/D"
    assert transpose_chord_symbol("Bb", 2) == "C"


def test_single_note_lines_get_no_chord_names():
    scale = make_notes([(i * 240, 240, m) for i, m in enumerate([57, 60, 62, 64, 67, 69, 72, 74])])
    assert label_chords(scale, TPQ) == []
