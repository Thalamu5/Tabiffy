"""Stage 1b: MIDI input shortcut. Reads a .mid file into raw notes per instrument.

The output is a `TabiffyScore` whose tracks hold the *source* notes (no string/fret
yet). Each (MIDI track, channel) pair with notes becomes one track. Drum channel
(10) is skipped (drum notation is a non-goal).
"""

from __future__ import annotations

import io
from collections import defaultdict

import mido

from .models import Meta, Note, TabiffyScore, TempoPoint, Track

TPQ = 960
DRUM_CHANNEL = 9

# mido key signature names -> readable key names
_MAJOR_KEYS = {"C", "G", "D", "A", "E", "B", "F#", "C#", "F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"}


def instrument_for_program(program: int) -> str:
    if 24 <= program <= 31:
        return "guitar"
    if 32 <= program <= 39:
        return "bass"
    if 0 <= program <= 7:
        return "piano"
    return "other"


def _key_name(mido_key: str) -> str:
    if mido_key.endswith("m"):
        return f"{mido_key[:-1]} minor"
    return f"{mido_key} major" if mido_key in _MAJOR_KEYS else mido_key


def read_midi(data: bytes, source_file: str = "") -> TabiffyScore:
    mid = mido.MidiFile(file=io.BytesIO(data))
    if mid.type == 2:
        raise ValueError("MIDI type 2 (asynchronous tracks) is not supported")
    scale = TPQ / mid.ticks_per_beat

    tempo_map: list[TempoPoint] = []
    time_sig: tuple[int, int] | None = None
    key = ""
    title = ""
    # (track index, channel) -> data
    groups: dict[tuple[int, int], dict] = defaultdict(lambda: {"notes": [], "program": None, "name": ""})
    track_names: dict[int, str] = {}

    for ti, track in enumerate(mid.tracks):
        tick = 0
        open_notes: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
        programs: dict[int, int] = {}
        for msg in track:
            tick += msg.time
            t = round(tick * scale)
            if msg.is_meta:
                if msg.type == "set_tempo":
                    bpm = round(mido.tempo2bpm(msg.tempo), 3)
                    if tempo_map and tempo_map[-1].tick == t:
                        tempo_map[-1] = TempoPoint(tick=t, bpm=bpm)
                    else:
                        tempo_map.append(TempoPoint(tick=t, bpm=bpm))
                elif msg.type == "time_signature" and time_sig is None:
                    time_sig = (msg.numerator, msg.denominator)
                elif msg.type == "key_signature" and not key:
                    key = _key_name(msg.key)
                elif msg.type == "track_name":
                    track_names[ti] = msg.name.strip()
                    if ti == 0 and not title:
                        title = msg.name.strip()
                continue
            if msg.type == "program_change":
                programs[msg.channel] = msg.program
                g = groups[(ti, msg.channel)]
                if g["program"] is None:
                    g["program"] = msg.program
            elif msg.type == "note_on" and msg.velocity > 0:
                open_notes[(msg.channel, msg.note)].append((t, msg.velocity))
            elif msg.type in ("note_off", "note_on"):
                stack = open_notes.get((msg.channel, msg.note))
                if stack:
                    start, vel = stack.pop(0)
                    if t > start:
                        groups[(ti, msg.channel)]["notes"].append((start, t - start, msg.note, vel))
        # Close notes that never received a note-off.
        for (ch, pitch), stack in open_notes.items():
            for start, vel in stack:
                groups[(ti, ch)]["notes"].append((start, max(TPQ // 4, round(tick * scale) - start), pitch, vel))

    if not tempo_map or tempo_map[0].tick != 0:
        tempo_map.insert(0, TempoPoint(tick=0, bpm=tempo_map[0].bpm if tempo_map else 120.0))

    tracks: list[Track] = []
    note_counter = 0
    for (ti, ch), g in sorted(groups.items()):
        if ch == DRUM_CHANNEL or not g["notes"]:
            continue
        program = g["program"] if g["program"] is not None else 0
        source = instrument_for_program(program)
        notes = []
        for start, dur, pitch, vel in sorted(g["notes"]):
            note_counter += 1
            notes.append(Note(id=f"n{note_counter}", tick=start, duration_ticks=dur, midi=pitch, velocity=vel))
        name = track_names.get(ti) or f"Track {len(tracks) + 1}"
        if sum(1 for k in groups if k[0] == ti and groups[k]["notes"]) > 1:
            name = f"{name} (ch {ch + 1})"
        tracks.append(
            Track(
                id=f"src{len(tracks) + 1}",
                name=name,
                source_instrument=source,
                target_instrument="bass" if source == "bass" else "guitar",
                program=program,
                notes=notes,
                source_track_index=len(tracks),
            )
        )

    if not tracks:
        raise ValueError("The MIDI file contains no (non-drum) notes")

    return TabiffyScore(
        meta=Meta(
            title=title or source_file.rsplit(".", 1)[0],
            source_file=source_file,
            bpm=tempo_map[0].bpm,
            time_signature=time_sig or (4, 4),
            key=key,
        ),
        tempo_map=tempo_map,
        ticks_per_quarter=TPQ,
        tracks=tracks,
    )
