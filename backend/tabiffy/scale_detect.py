"""Key and scale detection with plain-language reasons (shown when you click the key).

Two questions are answered separately: which note is "home" (the tonic) and which scale the notes
fit. Many scales share the same notes (A minor and C major), so the tonic decides between them.
"""

from __future__ import annotations

import numpy as np

from .models import ChordLabel, KeyAnalysis, Note, ScaleMatch
from .pitch import NOTE_NAMES_FLAT, NOTE_NAMES_SHARP

# name -> (intervals from the tonic, family shown in the UI, prior). The prior is a small penalty
# for rarer scales so they only win when the notes really call for them.
SCALES: dict[str, tuple[tuple[int, ...], str, float]] = {
    "major": ((0, 2, 4, 5, 7, 9, 11), "Major modes", 0.0),
    "natural minor": ((0, 2, 3, 5, 7, 8, 10), "Major modes", 0.0),
    "Dorian": ((0, 2, 3, 5, 7, 9, 10), "Major modes", 0.03),
    "Phrygian": ((0, 1, 3, 5, 7, 8, 10), "Major modes", 0.04),
    "Lydian": ((0, 2, 4, 6, 7, 9, 11), "Major modes", 0.04),
    "Mixolydian": ((0, 2, 4, 5, 7, 9, 10), "Major modes", 0.03),
    "Locrian": ((0, 1, 3, 5, 6, 8, 10), "Major modes", 0.07),
    "harmonic minor": ((0, 2, 3, 5, 7, 8, 11), "Harmonic minor modes", 0.03),
    "Phrygian Dominant": ((0, 1, 4, 5, 7, 8, 10), "Harmonic minor modes", 0.04),
    "Ukrainian Dorian": ((0, 2, 3, 6, 7, 9, 10), "Harmonic minor modes", 0.07),
    "melodic minor": ((0, 2, 3, 5, 7, 9, 11), "Melodic minor modes", 0.04),
    "Lydian Dominant": ((0, 2, 4, 6, 7, 9, 10), "Melodic minor modes", 0.06),
    "Mixolydian b6": ((0, 2, 4, 5, 7, 8, 10), "Melodic minor modes", 0.06),
    "Altered": ((0, 1, 3, 4, 6, 8, 10), "Melodic minor modes", 0.08),
    "Hungarian minor": ((0, 2, 3, 6, 7, 8, 11), "Other", 0.07),
    "Double Harmonic major": ((0, 1, 4, 5, 7, 8, 11), "Other", 0.07),
    "major pentatonic": ((0, 2, 4, 7, 9), "Pentatonic and blues", 0.01),
    "minor pentatonic": ((0, 3, 5, 7, 10), "Pentatonic and blues", 0.01),
    "blues": ((0, 3, 5, 6, 7, 10), "Pentatonic and blues", 0.02),
}
# Degree names used when explaining what makes a scale different from plain major/minor.
_DEGREES = ["root", "flat 2nd", "2nd", "minor 3rd", "major 3rd", "4th", "sharp 4th / flat 5th", "5th",
            "flat 6th", "6th", "flat 7th", "major 7th"]  # fmt: skip
_LETTERS = "CDEFGAB"
_LETTER_PC = [0, 2, 4, 5, 7, 9, 11]
OUTSIDE_PENALTY = 1.5  # notes outside the scale count against it this much more than notes inside count for it
MISSING_PENALTY = 0.04  # per scale note never played (so a 5-note scale wins when only 5 notes are used)
TONIC_WEIGHT = 0.6  # how much the "home note" evidence matters versus how well the notes fit
TRIAD_WEIGHT = 0.5  # how much the home chord being prominent matters


def _norm(v: np.ndarray) -> np.ndarray:
    s = v.sum()
    return v / s if s > 0 else v


def tonic_evidence(notes: list[Note], chords: list[ChordLabel], beat: int) -> dict[str, np.ndarray]:
    """Four hints for which note is home, each a share per pitch class (C=0 ... B=11)."""
    played = np.zeros(12)
    bass = np.zeros(12)
    ends = np.zeros(12)
    roots = np.zeros(12)
    for n in notes:
        played[n.midi % 12] += n.duration_ticks * n.velocity / 127
    # Bass: the lowest note sounding on each beat.
    if notes:
        last = max(n.tick + n.duration_ticks for n in notes)
        lowest = np.full(last // beat + 1, 999)
        for n in notes:
            for b in range(n.tick // beat, (n.tick + n.duration_ticks - 1) // beat + 1):
                lowest[b] = min(lowest[b], n.midi)
        for m in lowest[lowest < 999]:
            bass[int(m) % 12] += 1
    # Phrase ends: a note followed by at least a beat of silence, plus the very last note.
    by_start = sorted(notes, key=lambda n: n.tick)
    for i, n in enumerate(by_start):
        nxt = by_start[i + 1].tick if i + 1 < len(by_start) else None
        if nxt is None or nxt - (n.tick + n.duration_ticks) >= beat:
            ends[n.midi % 12] += 1
    for c in chords:
        if c.pcs:
            roots[_chord_root(c)] += c.duration_ticks
    # A handful of phrase ends is weak evidence (one loop ending proves little), so it is scaled down.
    ends_trust = ends.sum() / (ends.sum() + 4)
    return {"played": _norm(played), "bass": _norm(bass), "ends": _norm(ends) * ends_trust, "roots": _norm(roots)}


def _chord_root(c: ChordLabel) -> int:
    name = c.symbol.split("/")[0]
    root = name[:2] if len(name) > 1 and name[1] in "#b" else name[:1]
    names = NOTE_NAMES_SHARP if "#" in root else NOTE_NAMES_FLAT
    return names.index(root) if root in names else c.pcs[0]


def _spell(tonic: int, intervals: tuple[int, ...]) -> list[str]:
    """Note names for a scale, using each letter once for 7-note scales (F# G A# B C# D E)."""
    best: list[str] | None = None
    for names in (NOTE_NAMES_SHARP, NOTE_NAMES_FLAT):
        start = names[tonic]
        if len(intervals) != 7:
            spelled = [names[(tonic + i) % 12] for i in intervals]
        else:
            letter = _LETTERS.index(start[0])
            spelled = []
            for k, i in enumerate(intervals):
                lt = (letter + k) % 7
                diff = ((tonic + i) - _LETTER_PC[lt]) % 12
                acc = {0: "", 1: "#", 11: "b", 2: "##", 10: "bb"}.get(diff)
                spelled.append(_LETTERS[lt] + acc if acc is not None else names[(tonic + i) % 12])
        score = sum(len(x) - 1 for x in spelled) + 5 * sum(len(x) > 2 for x in spelled)
        if best is None or score < sum(len(x) - 1 for x in best) + 5 * sum(len(x) > 2 for x in best):
            best = spelled
    assert best is not None
    return best


def analyze_key(notes: list[Note], chords: list[ChordLabel], beat: int, top: int = 3) -> KeyAnalysis | None:
    """Rank every (tonic, scale) pair and explain the winner. None when there are no notes."""
    if not notes:
        return None
    ev = tonic_evidence(notes, chords, beat)
    played = ev["played"]
    # Home note: mostly what's played most and sits in the bass; phrase ends and chord roots help.
    home = 0.35 * played + 0.3 * ev["bass"] + 0.15 * ev["ends"] + 0.2 * ev["roots"]
    home = home / home.max() if home.max() > 0 else home

    ranked: list[tuple[float, int, str, float]] = []
    for tonic in range(12):
        for name, (iv, _, prior) in SCALES.items():
            pcs = [(tonic + i) % 12 for i in iv]
            inside = float(played[pcs].sum())
            missing = sum(1 for pc in pcs if played[pc] < 0.01)
            fit = inside - OUTSIDE_PENALTY * (1 - inside) - MISSING_PENALTY * missing - prior
            # The home chord (root, 3rd, 5th of this scale) should be heard a lot.
            third = 4 if 4 in iv else 3
            fifth = 7 if 7 in iv else 6
            triad = played[tonic] + played[(tonic + third) % 12] + played[(tonic + fifth) % 12]
            ranked.append((fit + TONIC_WEIGHT * home[tonic] + TRIAD_WEIGHT * triad, tonic, name, inside))
    ranked.sort(reverse=True)

    matches: list[ScaleMatch] = []
    best_score = ranked[0][0]
    for score, tonic, name, inside in ranked:
        if len(matches) == top:
            break
        if any(m.tonic_pc == tonic and m.name == name for m in matches):
            continue
        iv, family, _ = SCALES[name]
        notes_ = _spell(tonic, iv)
        matches.append(
            ScaleMatch(
                tonic=notes_[0],
                tonic_pc=tonic,
                name=name,
                label=f"{notes_[0]} {name}",
                family=family,
                notes=notes_,
                pcs=[(tonic + i) % 12 for i in iv],
                fit=round(inside, 3),
                relative=round(best_score - score, 3),
            )
        )
    best = matches[0]
    margin = matches[1].relative if len(matches) > 1 else 1.0
    confidence = "high" if margin > 0.15 else "medium" if margin > 0.05 else "low"
    return KeyAnalysis(
        key=_key_name(best),
        scale=best,
        alternatives=matches[1:],
        confidence=confidence,
        histogram=[round(float(x), 4) for x in played],
        reasons=_reasons(best, matches[1:], ev),
    )


def _key_name(m: ScaleMatch) -> str:
    """Plain major/minor key for the header pill, from the scale's 3rd."""
    iv = SCALES[m.name][0]
    return f"{m.tonic} {'major' if 4 in iv else 'minor'}"


def _reasons(best: ScaleMatch, alts: list[ScaleMatch], ev: dict[str, np.ndarray]) -> list[str]:
    """Up to four short, plain sentences explaining the result."""
    t = best.tonic_pc
    out: list[str] = []
    hints = [
        ("the note played the most", ev["played"]),
        ("the most common bass note", ev["bass"]),
        ("where phrases end", ev["ends"]),
        ("the most common chord root", ev["roots"]),
    ]
    # Only hints where this note clearly leads (not tied with another note) count as reasons.
    agree = [label for label, v in hints if v.sum() > 0 and v[t] > 1.1 * np.max(np.delete(v, t))]
    if agree:
        out.append(
            f"{best.tonic} feels like home: it's {', '.join(agree[:-1])}{' and ' if len(agree) > 1 else ''}{agree[-1]}."
        )
    else:
        out.append(f"{best.tonic} is the best overall fit for the home note, though no single hint points to it alone.")
    out.append(f"{round(best.fit * 100)}% of what's played fits {best.label} ({' '.join(best.notes)}).")

    # What sets it apart from plain major/minor on the same root.
    iv = set(SCALES[best.name][0])
    if len(iv) == 7 and best.name not in ("major", "natural minor"):
        ref_name = "major" if 4 in iv else "natural minor"
        ref = set(SCALES[ref_name][0])
        added = sorted(iv - ref)
        if added:
            spelled = dict(zip(SCALES[best.name][0], best.notes, strict=True))
            parts = [f"{spelled[i]} (the {_DEGREES[i]})" for i in added]
            out.append(f"What makes it {best.name} rather than {ref_name}: {' and '.join(parts)}.")
    if alts and alts[0].relative < 0.08:
        out.append(f"Close second: {alts[0].label}. It fits almost as well, so trust your ear here.")
    return out
