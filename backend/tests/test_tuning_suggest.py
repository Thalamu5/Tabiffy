"""Tuning suggestions on riffs whose tuning is known."""

import pytest
from conftest import make_notes

from tabiffy.models import TabiffyScore, Track
from tabiffy.pitch import name_to_midi as m
from tabiffy.tuning_suggest import suggest_tunings
from tabiffy.tunings import TUNINGS

E = 240  # 16th note


def riff(*events):
    """events: (beat_offset_in_16ths, [note names]) repeated 4 times."""
    spec, t = [], 0
    for _ in range(4):
        for step, names in events:
            for n in names:
                spec.append((t + step * E, E * 2, m(n)))
        t += 16 * E
    return spec


def score_for(spec):
    notes = make_notes(spec)
    src = Track(id="s", name="g", source_instrument="guitar", notes=notes, source_track_index=0)
    return TabiffyScore(tracks=[src]), src


def best(spec, **kw):
    score, src = score_for(spec)
    return [s.key for s in suggest_tunings(score, src, **kw)]


def test_standard_open_chords():
    spec = riff(
        (0, ["E2", "B2", "E3", "G#3", "B3", "E4"]),
        (8, ["A2", "E3", "A3", "C#4", "E4"]),
        (12, ["D3", "A3", "D4", "F#4"]),
    )
    assert best(spec)[0] == "standard"


def test_drop_d_power_chords():
    # one-finger power chords on the low three strings, chugging on open D
    spec = riff(
        (0, ["D2", "A2", "D3"]),
        (2, ["D2"]),
        (3, ["D2"]),
        (4, ["F2", "C3", "F3"]),
        (6, ["D2"]),
        (8, ["G2", "D3", "G3"]),
        (10, ["D2"]),
        (12, ["F2", "C3", "F3"]),
        (14, ["E2", "B2", "E3"]),
    )
    assert best(spec)[0] == "drop-d"


def test_drop_c_power_chords():
    spec = riff(
        (0, ["C2", "G2", "C3"]),
        (2, ["C2"]),
        (3, ["C2"]),
        (4, ["D#2", "A#2", "D#3"]),
        (6, ["C2"]),
        (8, ["F2", "C3", "F3"]),
        (10, ["C2"]),
        (12, ["D#2", "A#2", "D#3"]),
        (14, ["D2", "A2", "D3"]),
    )
    assert best(spec)[0] == "drop-c"


def test_seven_string_low_b_with_high_lead():
    spec = riff(
        (0, ["B1", "F#2", "B2"]),
        (2, ["B1"]),
        (4, ["E2", "B2"]),
        (8, ["E4"]),
        (9, ["G4"]),
        (10, ["B4"]),
        (11, ["E5"]),
        (12, ["D5"]),
        (14, ["B4"]),
    )
    top = best(spec)
    assert top[0] in ("7-string-b", "b-standard", "drop-b")
    assert any(TUNINGS[k]["strings"] == 7 for k in top)


def test_eight_string_low_f_sharp():
    spec = riff(
        (0, ["F#1", "C#2", "F#2"]), (2, ["F#1"]), (3, ["F#1"]), (4, ["A1", "E2"]), (8, ["E4", "G4"]), (12, ["B3"])
    )
    assert TUNINGS[best(spec)[0]]["strings"] == 8


def test_limit_to_string_count():
    spec = riff((0, ["C2", "G2", "C3"]), (4, ["D#2", "A#2"]))
    assert all(TUNINGS[k]["strings"] == 7 for k in best(spec, strings={7}))


def test_suggestions_explain_themselves():
    score, src = score_for(riff((0, ["C2", "G2", "C3"]), (2, ["C2"]), (4, ["D#2", "A#2", "D#3"])))
    s = suggest_tunings(score, src)
    assert s[0].relative == 0 and s[0].reason.startswith("Lowest note heard: C2")
    assert all(x.score >= s[0].score for x in s)


def test_auto_tuning_is_applied_on_import(fixtures_dir):
    from tabiffy.pipeline import import_midi

    _, out = import_midi((fixtures_dir / "chord_progression.mid").read_bytes(), "x.mid", tuning="auto")
    t = out.tracks[0]
    assert t.tuning_detected and t.tuning_suggestions
    assert t.tuning == TUNINGS["standard"]["notes"]
    _, fixed = import_midi((fixtures_dir / "chord_progression.mid").read_bytes(), "x.mid", tuning="drop-c")
    assert fixed.tracks[0].tuning == TUNINGS["drop-c"]["notes"] and not fixed.tracks[0].tuning_detected


@pytest.mark.parametrize("key", [k for k, t in TUNINGS.items() if t["instrument"] == "guitar"])
def test_every_guitar_preset_solves(key):
    from tabiffy.pipeline import ResolveOptions, build_track

    score, src = score_for(riff((0, ["E2", "B2", "E3"]), (4, ["A3", "C4"]), (8, ["E4"])))
    track, _ = build_track(score, src, ResolveOptions(tuning=TUNINGS[key]["notes"]), "t")
    assert len(track.tuning) == TUNINGS[key]["strings"]
    assert all(1 <= n.string <= len(track.tuning) for n in track.notes)


def test_drop_a_six_string():
    # Chugging on the open low A with one-finger power chords: a Drop A riff.
    spec = riff(
        (0, ["A1", "E2", "A2"]),
        (2, ["A1"]),
        (3, ["A1"]),
        (4, ["C2", "G2", "C3"]),
        (6, ["A1"]),
        (8, ["D2", "A2", "D3"]),
        (10, ["A1"]),
        (12, ["C2", "G2", "C3"]),
        (14, ["B1", "F#2", "B2"]),
    )
    assert best(spec)[0] in ("drop-a", "7-string-drop-a")
    assert "drop-a" in best(spec)


def test_drop_g_seven_string():
    # Open low G chugs plus a high lead line only a 7-string reaches comfortably.
    spec = riff(
        (0, ["G1", "D2", "G2"]),
        (2, ["G1"]),
        (3, ["G1"]),
        (4, ["A#1", "F2", "A#2"]),
        (6, ["G1"]),
        (8, ["D4"]),
        (9, ["F4"]),
        (10, ["A4"]),
        (11, ["D5"]),
        (12, ["C5"]),
        (14, ["A4"]),
    )
    assert best(spec)[0] == "7-string-drop-g"
