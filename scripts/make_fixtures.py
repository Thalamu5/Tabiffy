"""Generate the small, self-made (rights-cleared) MIDI fixtures in /fixtures.

Run:  python scripts/make_fixtures.py
"""

from __future__ import annotations

from pathlib import Path

import mido

OUT = Path(__file__).resolve().parent.parent / "fixtures"
TPB = 480


def write(
    name: str,
    tracks: list[tuple[str, int, int, list[tuple[int, int, int]]]],
    bpm: float = 100,
    ts: tuple[int, int] = (4, 4),
) -> None:
    """tracks: (name, program, channel, [(start_tick, duration_ticks, pitch)])"""
    mid = mido.MidiFile(type=1, ticks_per_beat=TPB)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("track_name", name=name.replace("_", " ").title(), time=0))
    meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    meta.append(mido.MetaMessage("time_signature", numerator=ts[0], denominator=ts[1], time=0))
    mid.tracks.append(meta)
    for tname, program, ch, notes in tracks:
        tr = mido.MidiTrack()
        tr.append(mido.MetaMessage("track_name", name=tname, time=0))
        tr.append(mido.Message("program_change", program=program, channel=ch, time=0))
        events = []
        for start, dur, pitch in notes:
            events.append((start, 1, mido.Message("note_on", note=pitch, velocity=90, channel=ch)))
            events.append((start + dur, 0, mido.Message("note_off", note=pitch, velocity=0, channel=ch)))
        events.sort(key=lambda e: (e[0], e[1]))
        now = 0
        for t, _, msg in events:
            msg.time = t - now
            now = t
            tr.append(msg)
        mid.tracks.append(tr)
    OUT.mkdir(exist_ok=True)
    mid.save(OUT / f"{name}.mid")


def chord_progression() -> None:
    bar = TPB * 4
    voicings = {  # open-position voicings, low -> high
        "C": [48, 52, 55, 60, 64],
        "G": [43, 47, 50, 55, 59, 67],
        "Am": [45, 52, 57, 60, 64],
        "F": [41, 48, 53, 57, 60, 65],
    }
    notes = []
    for i, name in enumerate(["C", "G", "Am", "F"] * 2):
        for beat in range(2):
            for p in voicings[name]:
                notes.append((i * bar + beat * 2 * TPB, 2 * TPB, p))
    write("chord_progression", [("Acoustic Guitar", 25, 0, notes)], bpm=90)


def pentatonic_riff() -> None:
    scale = [45, 48, 50, 52, 55, 57, 60, 62, 64, 67, 69, 72]
    line = scale + scale[-2::-1] + [69, 67, 64, 62, 60, 57, 55, 52]
    s = TPB // 4
    write("pentatonic_riff", [("Lead Guitar", 29, 0, [(i * s, s, p) for i, p in enumerate(line)])], bpm=80)


def piano_piece() -> None:
    melody = [72, 74, 76, 77, 79, 77, 76, 74, 72, 76, 79, 84, 79, 76, 72, 72]
    bass = [48, 55, 52, 55, 45, 52, 48, 52, 41, 48, 45, 48, 43, 50, 48, 48]
    rh = [(i * TPB, TPB, p) for i, p in enumerate(melody)]
    lh = [(i * TPB, TPB, p) for i, p in enumerate(bass)]
    write("piano_two_hands", [("Piano RH", 0, 0, rh), ("Piano LH", 0, 1, lh)], bpm=110)


def bass_line() -> None:
    roots = [28, 28, 31, 33, 33, 31, 28, 35]  # E1 G1 A1 ... (bass sounds an octave below written)
    notes = []
    for i, r in enumerate(roots):
        notes += [
            (i * TPB * 2, TPB, r),
            (i * TPB * 2 + TPB, TPB // 2, r + 12),
            (i * TPB * 2 + 3 * TPB // 2, TPB // 2, r + 7),
        ]
    write("bass_line", [("Bass", 33, 0, notes)], bpm=120)


def flute_melody() -> None:
    """A high melody (non-guitar instrument) that must be moved into guitar range."""
    tune = [91, 93, 95, 96, 98, 96, 95, 93, 91, 88, 91, 86]
    write("flute_melody", [("Flute", 73, 0, [(i * TPB, TPB, p) for i, p in enumerate(tune)])], bpm=96)


if __name__ == "__main__":
    chord_progression()
    pentatonic_riff()
    piano_piece()
    bass_line()
    flute_melody()
    print("wrote", sorted(p.name for p in OUT.glob("*.mid")))
