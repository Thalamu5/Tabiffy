"""Only notes that were actually played survive transcription (no re-reported ringing notes or echoes)."""

from tabiffy.audio.transcribe import RawNote, keep_struck_notes


def note(start, end, pitch, rise, attack=1.0, level=-6.0):
    return RawNote(start, end, pitch, 0.6, attack, 0.0, rise, level)


def test_ringing_notes_reported_again_are_merged():
    # A2 is played once; when E3 starts, A2 (still ringing) is reported again with no rise in loudness.
    notes = [note(0.0, 0.4, 45, 30), note(0.4, 0.8, 52, 40), note(0.4, 0.9, 45, 0.5, attack=0.6)]
    kept = keep_struck_notes(notes)
    assert [(n.pitch, n.start) for n in kept] == [(45, 0.0), (52, 0.4)]
    assert kept[0].end == 0.9  # the A2 just rings on


def test_repeated_notes_with_their_own_attack_are_kept():
    # A bass player repeating the same note: little loudness change, but a clear pluck each time.
    notes = [note(i * 0.25, i * 0.25 + 0.24, 40, 30 if i == 0 else 2, attack=0.9) for i in range(4)]
    assert len(keep_struck_notes(notes)) == 4


def test_overtones_and_echoes_are_dropped():
    notes = [
        note(0.0, 0.5, 57, 35, level=-3),
        note(0.0, 0.5, 64, 0.5, attack=1.0),  # starts with A3 but never got louder: an overtone
        note(0.3, 0.4, 52, 8, level=-33),  # 30 dB quieter than the melody around it: an echo
    ]
    assert [n.pitch for n in keep_struck_notes(notes)] == [57]
