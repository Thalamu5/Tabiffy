"""Two-hand tapping: the 16-1-4 pattern from a real tapping song, as 16th-note triplets."""

from conftest import make_notes

from tabiffy.models import SolverSettings, TabiffyScore, Track
from tabiffy.pipeline import ResolveOptions, build_track, single_line
from tabiffy.solver import load_config, solve_track
from tabiffy.tunings import STANDARD_GUITAR, tuning_midi

SEXT = 160  # a 16th-note triplet at 960 ticks per quarter


def pattern(frets=(16, 1, 4), repeats=8, open_midi=64, ring=SEXT):
    """Tap the first fret, pull off to the second, hammer on to the third (all on one string)."""
    spec = []
    for r in range(repeats):
        for k, f in enumerate(frets):
            spec.append(((r * 3 + k) * SEXT, ring, open_midi + f))
    return make_notes(spec)


def link(notes):
    # What audio detection provides: pull-off from the tap, hammer-on after it.
    for a, b in zip(notes, notes[1:], strict=False):
        if (a.midi - 64, b.midi - 64) in ((16, 1), (1, 4)):
            a.techniques, a.legato_to = ["pull" if b.midi < a.midi else "hammer"], b.id


def solve(notes, tapping):
    return sorted(
        solve_track(notes, tuning_midi(STANDARD_GUITAR), 0, load_config(), tapping=tapping).notes, key=lambda n: n.tick
    )


def test_tapping_mode_writes_the_pattern_on_one_string():
    notes = pattern()
    link(notes)
    res = solve(notes, tapping=True)
    assert {n.string for n in res} == {1}
    assert [n.fret for n in res[:6]] == [16, 1, 4, 16, 1, 4]
    taps = [n for n in res if "tap" in n.techniques]
    assert taps and all(n.fret == 16 and n.finger is None for n in taps)
    assert all("tap" not in n.techniques for n in res if n.fret != 16)


def test_without_tapping_mode_nothing_is_tapped():
    notes = pattern()
    link(notes)
    res = solve(notes, tapping=False)
    assert all("tap" not in n.techniques for n in res)
    # A 15-fret jump can't be fretted fast, so the notes get spread over strings instead.
    assert len({n.string for n in res}) > 1


def test_ordinary_lines_are_not_tapped_in_tapping_mode():
    # A small-interval scale run should still be fretted normally.
    notes = make_notes([(i * 240, 240, m) for i, m in enumerate([64, 66, 67, 69, 71, 72, 74, 76])])
    assert all("tap" not in n.techniques for n in solve(notes, tapping=True))


def test_ringing_tapped_notes_become_one_line():
    # Each note rings for a whole beat (as transcription often hears tapped notes).
    notes = single_line(pattern(ring=960), 960)
    assert all(n.duration_ticks == SEXT for n in notes[:-1])


def test_tapping_setting_flows_through_build_track():
    notes = pattern(ring=960)
    src = Track(id="s", name="g", source_instrument="guitar", notes=notes, source_track_index=0)
    score = TabiffyScore(tracks=[src])
    opts = ResolveOptions(settings=SolverSettings(tapping=True, quantize="1/16+triplets"))
    track, _ = build_track(score, src, opts, "t")
    assert any("tap" in n.techniques for n in track.notes)
    assert {n.tick % SEXT for n in track.notes} == {0}  # stayed on the 16th-triplet grid


def test_tapping_recording_end_to_end(tmp_path):
    """A synthesized tapping run (tap 16, pull to 1, hammer to 4) through the whole audio pipeline."""
    import numpy as np
    import pytest

    pytest.importorskip("basic_pitch")
    from audio_synth import legato_line, write

    from tabiffy.audio.pipeline import import_audio

    segs = []
    for _ in range(16):
        segs += [(80, 0.1, "pick"), (65, 0.1, "pull"), (68, 0.1, "hammer")]  # 16th triplets at 100 bpm
    wav = write(tmp_path / "tap.wav", np.concatenate([legato_line(segs), np.zeros(22050)]))
    _, score = import_audio(
        wav, tmp_path / "work", "tap.wav", "guitar", SolverSettings(tapping=True), tuning="standard"
    )
    notes = sorted(score.tracks[0].notes, key=lambda n: n.tick)
    on_high = [n for n in notes if n.string == 1]
    assert len(on_high) >= 0.9 * len(notes)
    # The run's last notes fade out with looser timing, so allow a few off the triplet grid.
    assert sum(n.tick % SEXT == 0 for n in notes) >= 0.9 * len(notes)
    taps = [n for n in notes if "tap" in n.techniques]
    assert len(taps) >= 12 and all(n.fret == 16 for n in taps)
    pulls = [n for n in taps if "pull" in n.techniques and "suggestedTechnique" not in n.flags]
    assert len(pulls) >= 8
