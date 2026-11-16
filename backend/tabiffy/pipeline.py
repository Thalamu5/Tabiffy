"""Pipeline orchestration.

Import (MIDI, M1):   1b read MIDI -> 4 key -> 6 map/transpose -> 8 quantize -> 5 chords -> 7 solve
Resolve (stages 6-8 only): re-run mapping, quantization and the solver for one track with
new tuning/capo/target/transpose, keeping user-edited (locked) notes fixed.

Stage order note: quantization runs before the solver here, because the solver needs
clean time slices; chord labels are computed on the quantized notes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .chords import label_chords
from .key_detect import detect_key
from .mapping import assign_hands, comfort_range, instrument_range, map_to_range
from .midi_import import read_midi
from .models import CapoSuggestion, ChordLabel, Note, SolverSettings, TabiffyScore, Track
from .pitch import parse_pc, pc_name, transpose_chord_symbol
from .quantize import quantize_notes
from .scale_detect import analyze_key
from .solver import load_config, solve_track
from .timing import TempoMap
from .tunings import default_tuning, is_standard_guitar, tuning_midi

GM_PROGRAM = {"guitar": 25, "bass": 33, "piano": 0}  # steel guitar, finger bass, grand piano
SLICE_TOLERANCE_SECONDS = 0.03


@dataclass
class ResolveOptions:
    target: str = "guitar"
    tuning: list[str] | None = None
    capo: int = 0
    transpose: int = 0
    locked_notes: list[Note] = field(default_factory=list)
    settings: SolverSettings = field(default_factory=SolverSettings)


def _bar_ticks(score: TabiffyScore) -> int:
    num, den = score.meta.time_signature
    return round(num * 4 / den * score.ticks_per_quarter)


def _chord_lookup(chords: list[ChordLabel]):
    def at(tick: int) -> str | None:
        for c in chords:
            if c.tick <= tick < c.tick + c.duration_ticks:
                return c.symbol
        return None

    return at


def prepare_notes(score: TabiffyScore, source: Track, opts: ResolveOptions) -> list[Note]:
    """Stages 6 + 8 for one track: map into the instrument's range, then snap to the rhythm grid.
    These are all the notes the track should contain, before the solver drops any it can't fit."""
    s = opts.settings
    target = opts.target
    tuning = opts.tuning or default_tuning(target)
    open_midi = tuning_midi(tuning) if target != "piano" else []
    capo = opts.capo if target != "piano" else 0
    tpq = score.ticks_per_quarter

    # Locked notes replace their source counterparts (matched by id).
    locked = {n.id: n for n in opts.locked_notes}
    notes = [locked.get(n.id, n) for n in source.notes]
    notes += [n for nid, n in locked.items() if nid not in {m.id for m in source.notes}]

    # 6. mapping / transposition
    lo, hi = instrument_range(target, open_midi, capo, s.max_fret)
    native = source.source_instrument == target
    comfort = None if native else comfort_range(target, open_midi, capo)
    notes = map_to_range(notes, lo, hi, opts.transpose, phrase_gap_ticks=_bar_ticks(score), comfort=comfort)
    # 8. quantize (locked notes keep their timing)
    free = quantize_notes([n for n in notes if not n.user_edited], tpq, s.quantize)
    return sorted(free + [n for n in notes if n.user_edited], key=lambda n: (n.tick, n.midi))


def build_track(score: TabiffyScore, source: Track, opts: ResolveOptions, track_id: str) -> tuple[Track, float]:
    """Stages 6-8 for one track. Returns the output track and the solver cost."""
    cfg = load_config()
    s = opts.settings
    target = opts.target
    tuning = opts.tuning or default_tuning(target)
    open_midi = tuning_midi(tuning) if target != "piano" else []
    capo = opts.capo if target != "piano" else 0
    tpq = score.ticks_per_quarter
    tempo = TempoMap(score.tempo_map, tpq)
    notes = prepare_notes(score, source, opts)

    cost = 0.0
    if target == "piano":
        out_notes = assign_hands(notes)
    else:
        num, den = score.meta.time_signature
        chords = label_chords(notes, tpq, num, round(tpq * 4 / den))
        tol = 0 if s.quantize != "off" else tempo.ticks_for_seconds_at(0, SLICE_TOLERANCE_SECONDS)
        res = solve_track(
            notes,
            open_midi,
            capo,
            cfg,
            max_fret=s.max_fret,
            open_pref=s.open_string_preference,
            standard_tuning=target == "guitar" and is_standard_guitar(tuning),
            chords_at={n.tick: c for n in notes if (c := _chord_lookup(chords)(n.tick))},
            seconds_at=tempo.seconds,
            tolerance_ticks=tol,
            max_notes_per_slice=4 if s.simplify_chords else None,
        )
        out_notes, cost = res.notes, res.cost + 5.0 * len(res.dropped)

    track = Track(
        id=track_id,
        name=source.name,
        source_instrument=source.source_instrument,
        target_instrument=target,
        tuning=tuning if target != "piano" else [],
        capo=capo,
        transpose_semitones=opts.transpose,
        program=GM_PROGRAM[target],
        notes=out_notes,
        source_track_index=source.source_track_index,
    )
    return track, cost


def relabel_chords(score: TabiffyScore, source: TabiffyScore | None = None) -> None:
    """Name the chords. With `source`, uses every note each track should contain (after range
    mapping and quantizing), so notes the solver had to drop from a dense chord still count."""
    if source is None:
        notes = [n for t in score.tracks for n in t.notes]
    else:
        notes = []
        for i, t in enumerate(score.tracks):
            idx = t.source_track_index if t.source_track_index is not None else i
            if not 0 <= idx < len(source.tracks):
                notes += t.notes
                continue
            opts = ResolveOptions(
                target=t.target_instrument,
                tuning=t.tuning or None,
                capo=t.capo,
                transpose=t.transpose_semitones,
                settings=score.settings,
                locked_notes=[n for n in t.notes if n.user_edited],
            )
            notes += prepare_notes(source, source.tracks[idx], opts)
    num, den = score.meta.time_signature
    tpq = score.ticks_per_quarter
    beat = round(tpq * 4 / den)
    score.chords = label_chords(notes, tpq, num, beat)
    # Key and scale come from the same notes as the chords, so they follow transpose and edits.
    score.key_analysis = analyze_key(notes, score.chords, beat)
    if score.key_analysis:
        score.meta.key = score.key_analysis.key


def suggest_capo(score: TabiffyScore, source: Track, opts: ResolveOptions, max_capo: int = 7) -> CapoSuggestion:
    """Run the solver for capo 0..max_capo and return the cheapest (SPEC 5.3)."""
    best: CapoSuggestion | None = None
    for capo in range(max_capo + 1):
        o = ResolveOptions(
            target=opts.target, tuning=opts.tuning, capo=capo, transpose=opts.transpose, settings=opts.settings
        )
        _, cost = build_track(score, source, o, "tmp")
        # mild preference for no capo when costs are close
        cost += 0.5 * capo
        if best is None or cost < best.cost:
            best = CapoSuggestion(capo=capo, cost=round(cost, 2))
    assert best is not None
    key = score.meta.key
    if key and best.capo:
        tonic, _, mode = key.partition(" ")
        flats = tonic.endswith("b")
        best.shapes_key = f"{pc_name(parse_pc(tonic) + opts.transpose - best.capo, flats)} {mode}".strip()
    return best


def solve_all(
    source: TabiffyScore,
    settings: SolverSettings | None = None,
    previous: TabiffyScore | None = None,
    on_progress=None,
    tuning: str = "standard",
) -> TabiffyScore:
    """Build every output track from `source`. With `previous`, each track keeps the
    target/tuning/capo/transpose the user chose (matched by source track index).

    `tuning` applies to new guitar tracks: a preset key from tunings.TUNINGS, or "auto" to
    pick the best-fitting tuning from the notes (alternatives are stored on the track)."""
    from .tuning_suggest import suggest_tunings
    from .tunings import TUNINGS

    out = source.model_copy(deep=True)
    out.settings = settings or (previous.settings if previous else SolverSettings())
    out.tracks = []
    prev_by_src = {t.source_track_index: t for t in previous.tracks} if previous else {}
    for i, src in enumerate(source.tracks):
        if on_progress:
            on_progress(i / max(1, len(source.tracks)))
        prev = prev_by_src.get(src.source_track_index)
        if prev:
            opts = ResolveOptions(
                target=prev.target_instrument,
                tuning=prev.tuning or None,
                capo=prev.capo,
                transpose=prev.transpose_semitones,
                settings=out.settings,
            )
            track_id, name = prev.id, prev.name
        else:
            opts = ResolveOptions(target=src.target_instrument, settings=out.settings)
            track_id, name = f"t{i + 1}", src.name
        suggestions, detected = [], False
        if not prev and src.target_instrument == "guitar":
            if tuning == "auto":
                suggestions = suggest_tunings(source, src, out.settings)
                if suggestions:
                    opts.tuning, detected = suggestions[0].tuning, True
            elif TUNINGS.get(tuning, {}).get("instrument") == "guitar":
                opts.tuning = TUNINGS[tuning]["notes"]
        track, _ = build_track(source, src, opts, track_id)
        track.name = name
        if prev:
            track.tuning_suggestions, track.tuning_detected = prev.tuning_suggestions, prev.tuning_detected
        else:
            track.tuning_suggestions, track.tuning_detected = suggestions, detected
        out.tracks.append(track)
    relabel_chords(out, source)
    return out


def import_midi(
    data: bytes, filename: str, settings: SolverSettings | None = None, on_stage=None, tuning: str = "auto"
) -> tuple[TabiffyScore, TabiffyScore]:
    """Returns (source score with raw notes, solved output score)."""

    def stage(name: str, progress: float) -> None:
        if on_stage:
            on_stage(name, progress)

    stage("decode", 0.1)
    source = read_midi(data, filename)
    stage("analyze", 0.3)
    if not source.meta.key:
        source.meta.key = detect_key([n for t in source.tracks for n in t.notes])
    stage("solve", 0.5)
    out = solve_all(source, settings, on_progress=lambda f: stage("solve", 0.5 + 0.45 * f), tuning=tuning)
    return source, out


__all__ = [
    "import_midi",
    "solve_all",
    "build_track",
    "relabel_chords",
    "suggest_capo",
    "ResolveOptions",
    "transpose_chord_symbol",
]
