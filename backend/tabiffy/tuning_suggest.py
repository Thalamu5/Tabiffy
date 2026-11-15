"""Suggest a guitar tuning from the notes that were heard.

Each candidate tuning is tried with the real pipeline (range mapping, rhythm grid, fret
solver) and scored on:
- notes it can't play at all (below its lowest string) -> strong penalty,
- how hard the resulting tab is (solver cost per note: stretches, jumps, high frets,
  and a bonus for open strings, which is how drop-tuned riffs usually show themselves),
- low strings that nothing heard comes close to (more strings than the music needs),
- a small prior for how common the tuning is, so ties go to the familiar one.

It is evidence-based guessing, not certainty: the UI shows the top few with reasons.
"""

from __future__ import annotations

from .models import TabiffyScore, Track, TuningSuggestion
from .pitch import midi_to_name
from .tunings import TUNINGS, tuning_midi

OUT_OF_RANGE_WEIGHT = 6.0
DROPPED_WEIGHT = 3.0
MIN_LOW_NOTES = 3
# A few notes far below the rest are more often detection errors (octave mistakes, bass bleed)
# than a lower string, so the lowest 3% of notes may be ignored when judging range.
NOISE_FRACTION = 0.03
UNUSED_LOW_STRING_WEIGHT = (
    2.0  # per low string tuned well below anything heard (players tune the lowest string near the lowest note)
)


def candidates(instrument: str = "guitar", strings: set[int] | None = None) -> list[str]:
    return [k for k, t in TUNINGS.items() if t["instrument"] == instrument and (not strings or t["strings"] in strings)]


def suggest_tunings(
    score: TabiffyScore, source: Track, settings=None, strings: set[int] | None = None, top: int = 3
) -> list[TuningSuggestion]:
    from .pipeline import ResolveOptions, build_track, prepare_notes

    settings = settings or score.settings
    if not source.notes:
        return []
    results: list[TuningSuggestion] = []
    pitches = sorted(n.midi for n in source.notes)
    noise_allowance = max(MIN_LOW_NOTES - 1, int(NOISE_FRACTION * len(pitches)))
    lowest_heard = pitches[min(noise_allowance, len(pitches) - 1)]  # robust "lowest note"
    absolute_lowest = pitches[0]
    for key in candidates("guitar", strings):
        preset = TUNINGS[key]
        opts = ResolveOptions(target="guitar", tuning=preset["notes"], settings=settings)
        n = len(prepare_notes(score, source, opts)) or 1
        track, cost = build_track(score, source, opts, "tmp")
        low_open = min(tuning_midi(preset["notes"]))
        below = sum(1 for m in source.notes if m.midi < low_open)
        below_eff = below if below > noise_allowance else 0
        dropped = n - len(track.notes)
        # strings tuned more than a whole tone below anything heard are dead weight
        unused_low = sum(1 for o in tuning_midi(preset["notes"]) if o < lowest_heard - 2)
        value = (
            cost / n
            + OUT_OF_RANGE_WEIGHT * below_eff / n
            + DROPPED_WEIGHT * dropped / n
            + UNUSED_LOW_STRING_WEIGHT * unused_low
            + preset["prior"]
        )
        if below_eff:
            reason = f"{below} note{'s' if below != 1 else ''} below its lowest string ({midi_to_name(low_open)})"
        elif below:
            reason = f"fits all but {below} very low note{'s' if below != 1 else ''} (likely detection errors)"
        else:
            opens = sum(1 for x in track.notes if x.fret == 0)
            reason = f"fits every note; {round(100 * opens / max(1, len(track.notes)))}% open strings"
        results.append(
            TuningSuggestion(
                key=key,
                label=preset["label"],
                tuning=preset["notes"],
                strings=preset["strings"],
                score=round(value, 3),
                notes_below=below,
                reason=reason,
            )
        )
    results.sort(key=lambda r: r.score)
    best = results[0].score if results else 0
    for r in results:
        r.relative = round(r.score - best, 3)
    if results:
        low = midi_to_name(lowest_heard)
        if absolute_lowest < lowest_heard:
            low += f" (a few stray notes down to {midi_to_name(absolute_lowest)})"
        results[0].reason = f"Lowest note heard: {low}. " + results[0].reason
    return results[:top]
