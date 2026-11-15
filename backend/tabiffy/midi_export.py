"""TabiffyScore -> Standard MIDI File (one track per instrument, GM programs, tempo map)."""

from __future__ import annotations

import io

import mido

from .models import TabiffyScore


def score_to_midi(score: TabiffyScore) -> bytes:
    mid = mido.MidiFile(type=1, ticks_per_beat=score.ticks_per_quarter)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("track_name", name=score.meta.title or "Tabiffy", time=0))
    num, den = score.meta.time_signature
    meta.append(mido.MetaMessage("time_signature", numerator=num, denominator=den, time=0))
    now = 0
    for tp in sorted(score.tempo_map, key=lambda t: t.tick):
        meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tp.bpm), time=tp.tick - now))
        now = tp.tick
    mid.tracks.append(meta)

    channels = [c for c in range(16) if c != 9]
    for i, track in enumerate(score.tracks):
        ch = channels[i % len(channels)]
        tr = mido.MidiTrack()
        tr.append(mido.MetaMessage("track_name", name=track.name, time=0))
        tr.append(mido.Message("program_change", program=track.program, channel=ch, time=0))
        events = []
        for n in track.notes:
            events.append((n.tick, 1, mido.Message("note_on", note=n.midi, velocity=n.velocity, channel=ch)))
            events.append((n.tick + n.duration_ticks, 0, mido.Message("note_off", note=n.midi, channel=ch)))
        events.sort(key=lambda e: (e[0], e[1]))
        now = 0
        for t, _, msg in events:
            msg.time = t - now
            now = t
            tr.append(msg)
        mid.tracks.append(tr)
    buf = io.BytesIO()
    mid.save(file=buf)
    return buf.getvalue()
