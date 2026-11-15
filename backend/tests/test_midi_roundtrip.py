from tabiffy.midi_export import score_to_midi
from tabiffy.midi_import import read_midi
from tabiffy.pipeline import import_midi


def test_midi_import_reads_meta(fixtures_dir):
    s = read_midi((fixtures_dir / "chord_progression.mid").read_bytes(), "chord_progression.mid")
    assert s.meta.bpm == 90 and tuple(s.meta.time_signature) == (4, 4)
    assert s.tracks[0].source_instrument == "guitar"
    assert len(s.tracks[0].notes) == 88


def test_instrument_detection(fixtures_dir):
    piano = read_midi((fixtures_dir / "piano_two_hands.mid").read_bytes())
    assert {t.source_instrument for t in piano.tracks} == {"piano"}
    bass = read_midi((fixtures_dir / "bass_line.mid").read_bytes())
    assert bass.tracks[0].target_instrument == "bass"


def test_export_reimport_same_notes(fixtures_dir):
    _, score = import_midi((fixtures_dir / "pentatonic_riff.mid").read_bytes(), "x.mid")
    again = read_midi(score_to_midi(score))
    a = [(n.tick, n.duration_ticks, n.midi) for n in score.tracks[0].notes]
    b = [(n.tick, n.duration_ticks, n.midi) for n in again.tracks[0].notes]
    assert sorted(a) == sorted(b)
