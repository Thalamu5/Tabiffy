"""Choose string and fret for every note (SPEC 5.1). Notes starting together form a slice; each slice
gets its cheapest playable shapes, and a Viterbi search picks the path where the hand moves least.
This stays linear in song length, so long songs remain fast."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..models import Note
from .config import SolverConfig
from .fingering import assign_fingers
from .shapes import shape_positions

FREE_POSITIONS = 12  # hand positions considered for all-open voicings


@dataclass
class Slice:
    tick: int
    notes: list[Note]
    seconds: float = 0.0
    chord: str | None = None


@dataclass
class Voicing:
    """One way to play a slice: a (string, fret) for each note, with its own cost."""

    positions: list[tuple[int, int]]  # parallel to slice.notes: (string, fret)
    cost: float
    min_fret: int | None
    max_fret: int | None
    string_mask: int
    tapped: bool = False  # a single note played by the picking hand (two-hand tapping)


@dataclass
class SolveResult:
    notes: list[Note]
    cost: float
    dropped: list[Note] = field(default_factory=list)


def make_slices(notes: list[Note], tolerance_ticks: int = 0) -> list[Slice]:
    """Group notes that start together (within the tolerance) into slices."""
    slices: list[Slice] = []
    for n in sorted(notes, key=lambda n: (n.tick, n.midi)):
        if slices and n.tick - slices[-1].tick <= tolerance_ticks:
            if all(m.midi != n.midi for m in slices[-1].notes):
                slices[-1].notes.append(n)
            continue
        slices.append(Slice(tick=n.tick, notes=[n]))
    return slices


def note_priority(notes: list[Note], chord_pcs: set[int] | None = None) -> list[Note]:
    """Order notes by importance for dense-slice reduction (SPEC 5.3):
    bass note, then melody (top), then distinct chord tones, then the rest."""
    if len(notes) <= 2:
        return sorted(notes, key=lambda n: n.midi)
    by_pitch = sorted(notes, key=lambda n: n.midi)
    order = [by_pitch[0], by_pitch[-1]]
    seen_pcs = {by_pitch[0].midi % 12, by_pitch[-1].midi % 12}
    middle = by_pitch[1:-1]

    # chord tones not yet covered, then other new pitch classes, then duplicates
    def rank(n: Note) -> tuple[int, int]:
        pc = n.midi % 12
        if pc not in seen_pcs and chord_pcs and pc in chord_pcs:
            return (0, -n.midi)
        if pc not in seen_pcs:
            return (1, -n.midi)
        return (2, -n.midi)

    for n in sorted(middle, key=rank):
        order.append(n)
        seen_pcs.add(n.midi % 12)
    return order


class FretSolver:
    """Finds the easiest string/fret for every note of one track (see module doc)."""

    def __init__(
        self,
        open_midi: list[int],
        capo: int,
        max_fret: int,
        cfg: SolverConfig,
        open_pref: float = 1.0,
        standard_tuning: bool = False,
        tapping: bool = False,
    ):
        # strings numbered 1 = highest; open_midi is low -> high
        self.tapping = tapping
        self.n_strings = len(open_midi)
        self.open = {self.n_strings - i: m + capo for i, m in enumerate(open_midi)}
        self.max_fret = max_fret
        self.cfg = cfg
        self.open_pref = open_pref
        self.standard = standard_tuning
        self.capo = capo

    # ---- candidates -------------------------------------------------------
    def note_options(self, n: Note) -> list[tuple[int, int]]:
        if n.user_edited and n.string is not None and n.fret is not None:
            return [(n.string, n.fret)]
        opts = []
        for s, open_m in self.open.items():
            f = n.midi - open_m
            if 0 <= f <= self.max_fret:
                opts.append((s, f))
        return opts

    def voicing_cost(self, positions: list[tuple[int, int]], notes: list[Note], chord: str | None) -> float:
        """How hard a shape is on its own: span, fingers, skipped strings, high frets and open strings."""
        cfg = self.cfg
        fretted = [f for _, f in positions if f > 0]
        cost = 0.0
        if fretted:
            span = max(fretted) - min(fretted)
            if span == 4:
                cost += cfg.stretch4
            elif span >= 5:
                cost += cfg.stretch5
            fr = assign_fingers(positions, min(fretted))
            if not fr.feasible:
                cost += cfg.fingersImpossible
            elif fr.barre:
                cost += cfg.barre
            mean = sum(fretted) / len(fretted)
            cost += cfg.highFret * mean + cfg.highFretAbove12 * max(0.0, max(fretted) - 12)
        n_open = len(positions) - len(fretted)
        bonus = cfg.openStringBonus if len(positions) > 1 else cfg.openStringBonusSingleNote
        cost -= bonus * self.open_pref * n_open
        if len(positions) >= 3:
            strings = sorted(s for s, _ in positions)
            skipped = (strings[-1] - strings[0] + 1) - len(strings)
            cost += cfg.skippedString * skipped
        # pitch order should follow string order (higher note on a higher string)
        pairs = sorted(zip(notes, positions, strict=True), key=lambda p: p[0].midi)
        crossings = sum(1 for a, b in zip(pairs, pairs[1:], strict=False) if b[1][0] > a[1][0])
        cost += cfg.stringCrossing * crossings
        if chord and self.standard and len(positions) >= 2:
            from ..pitch import transpose_chord_symbol

            shape = shape_positions(transpose_chord_symbol(chord, -self.capo), self.n_strings)
            if shape and set(positions) <= shape:
                cost -= cfg.chordShapeBonus * len(positions) / 2
        return cost

    def voicings(self, sl: Slice) -> list[Voicing]:
        """All playable shapes for a slice, cheapest first (plus tapped notes in tapping mode)."""
        notes = sorted(sl.notes, key=lambda n: -n.midi)
        options = [self.note_options(n) for n in notes]
        max_span = self.cfg.maxFingersSpanFrets
        found: list[list[tuple[int, int]]] = []

        def rec(i: int, used: int, acc: list[tuple[int, int]], lo: int, hi: int) -> None:
            """Depth-first search over string choices, skipping shapes the hand can't span."""
            if len(found) > 4000:
                return
            if i == len(notes):
                found.append(list(acc))
                return
            for s, f in options[i]:
                bit = 1 << s
                if used & bit:
                    continue
                nlo, nhi = (min(lo, f), max(hi, f)) if f > 0 else (lo, hi)
                if f > 0 and nhi - nlo > max_span:
                    continue
                acc.append((s, f))
                rec(i + 1, used | bit, acc, nlo, nhi)
                acc.pop()

        rec(0, 0, [], 99, -1)
        out = []
        for pos in found:
            fretted = [f for _, f in pos if f > 0]
            mask = 0
            for s, _ in pos:
                mask |= 1 << s
            out.append(
                Voicing(
                    positions=pos,
                    cost=self.voicing_cost(pos, notes, sl.chord),
                    min_fret=min(fretted) if fretted else None,
                    max_fret=max(fretted) if fretted else None,
                    string_mask=mask,
                )
            )
        sl.notes = notes  # keep note order in sync with voicing positions
        out.sort(key=lambda v: v.cost)
        out = out[: self.cfg.maxVoicingsPerSlice]
        # Tapping: a lone note may be tapped by the picking hand, which leaves the fretting hand where it is.
        if self.tapping and len(notes) == 1 and not notes[0].user_edited:
            for s, f in options[0]:
                if f >= self.cfg.tapMinFret:
                    cost = self.cfg.tap + self.cfg.highFretAbove12 * max(0, f - 12) / 2
                    out.append(Voicing([(s, f)], cost, None, None, 1 << s, tapped=True))
        return out

    # ---- DP ---------------------------------------------------------------
    def states(self, vs: list[Voicing]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Returns (voicing index, hand position, intrinsic cost, is_free) per state."""
        vi, pos, cost, free = [], [], [], []
        for i, v in enumerate(vs):
            if v.tapped:
                # The fretting hand stays put (any position), and the tapped fret must be out of its reach.
                tap_fret = v.positions[0][1]
                for p in range(1, min(self.max_fret, FREE_POSITIONS) + 1):
                    if tap_fret >= p + self.cfg.tapReach:
                        vi.append(i), pos.append(p), cost.append(v.cost), free.append(True)
                continue
            if v.min_fret is None:
                for p in range(1, min(self.max_fret, FREE_POSITIONS) + 1):
                    c = v.cost + self.cfg.openFarFromNut * max(0, p - 4)
                    vi.append(i), pos.append(p), cost.append(c), free.append(True)
                continue
            lo = max(
                1,
                v.max_fret
                - 3
                - (1 if v.max_fret - v.min_fret >= 4 else 0)
                - (1 if v.max_fret - v.min_fret >= 5 else 0),
            )
            for p in range(lo, v.min_fret + 1):
                c = v.cost + self.cfg.positionBehindIndex * (v.min_fret - p)
                vi.append(i), pos.append(p), cost.append(c), free.append(False)
        return np.array(vi), np.array(pos), np.array(cost, dtype=float), np.array(free)

    def transition(
        self,
        prev: tuple,
        cur: tuple,
        prev_vs: list[Voicing],
        cur_vs: list[Voicing],
        prev_slice: Slice,
        cur_slice: Slice,
    ) -> np.ndarray:
        """Cost of moving from each state of one slice to each state of the next.
        Covers hand movement, cutting ringing strings, and keeping linked notes on one string."""
        cfg = self.cfg
        p_vi, p_pos, _, p_free = prev
        c_vi, c_pos, _, c_free = cur
        gap = max(cur_slice.seconds - prev_slice.seconds, 0.02)
        speed = 1.0 + cfg.moveSpeed * min(4.0, 0.25 / gap)
        move = np.abs(p_pos[:, None] - c_pos[None, :]).astype(float)
        t = cfg.move * move * speed + cfg.bigJump * (move > cfg.bigJumpFrets) * speed
        t -= cfg.stayBonus * (move == 0)
        # Strings still ringing from the previous slice (a note that slides/hammers into the next one is
        # meant to be "cut" by it, so it doesn't count).
        cur_ids = {n.id for n in cur_slice.notes}
        ringing = []
        for v in prev_vs:
            mask = 0
            for (s, _), n in zip(v.positions, prev_slice.notes, strict=True):
                if n.tick + n.duration_ticks > cur_slice.tick and n.legato_to not in cur_ids:
                    mask |= 1 << s
            ringing.append(mask)
        ring = np.array(ringing)[p_vi]
        cur_mask = np.array([v.string_mask for v in cur_vs])[c_vi]
        t += cfg.cutRingingNote * ((ring[:, None] & cur_mask[None, :]) != 0)
        # Slides, hammer-ons and pull-offs only work on one string: penalize splitting a linked pair.
        for i, n in enumerate(prev_slice.notes):
            j = next((k for k, m in enumerate(cur_slice.notes) if m.id == n.legato_to), None) if n.legato_to else None
            if j is None:
                continue
            p_str = np.array([v.positions[i][0] for v in prev_vs])[p_vi]
            c_str = np.array([v.positions[j][0] for v in cur_vs])[c_vi]
            t += cfg.legatoStringChange * (p_str[:, None] != c_str[None, :])
        # Single-note lines: going up in pitch should not move to a lower string (and vice versa)
        if len(prev_slice.notes) == 1 and len(cur_slice.notes) == 1:
            dp = cur_slice.notes[0].midi - prev_slice.notes[0].midi
            p_str = np.array([v.positions[0][0] for v in prev_vs])[p_vi]
            c_str = np.array([v.positions[0][0] for v in cur_vs])[c_vi]
            ds = c_str[None, :] - p_str[:, None]  # +1 = moved to a lower-pitched string
            t += cfg.melodicCrossing * (((dp > 0) & (ds > 0)) | ((dp < 0) & (ds < 0)))
            if self.tapping:
                # Tapped runs stay on one string (tap, pull-off, hammer-on), so changing string costs extra.
                t += cfg.tapStringChange * (ds != 0)
        return t

    def solve(self, slices: list[Slice]) -> tuple[list[tuple[Voicing, int]], float, list[Note]]:
        """Viterbi over all slices; notes that can't be played are dropped and returned."""
        dropped: list[Note] = []
        all_vs: list[list[Voicing]] = []
        for sl in slices:
            vs = self.voicings(sl)
            if not vs or vs[0].cost >= self.cfg.fingersImpossible:
                # Reduce the slice until it becomes playable (SPEC 5.3)
                order = note_priority(sl.notes)
                locked = [n for n in order if n.user_edited]
                order = locked + [n for n in order if not n.user_edited]
                while len(order) > 1:
                    dropped.append(order.pop())
                    sl.notes = list(order)
                    vs = self.voicings(sl)
                    if vs and vs[0].cost < self.cfg.fingersImpossible:
                        break
            if not vs:
                dropped.extend(sl.notes)
                sl.notes = []
            all_vs.append(vs)

        keep = [i for i, vs in enumerate(all_vs) if vs]
        slices = [slices[i] for i in keep]
        all_vs = [all_vs[i] for i in keep]
        if not slices:
            return [], 0.0, dropped

        st = [self.states(vs) for vs in all_vs]
        dp = st[0][2].copy()
        backs = []
        for k in range(1, len(slices)):
            t = self.transition(st[k - 1], st[k], all_vs[k - 1], all_vs[k], slices[k - 1], slices[k])
            total = dp[:, None] + t
            best = np.argmin(total, axis=0)
            backs.append(best)
            dp = total[best, np.arange(total.shape[1])] + st[k][2]
        idx = int(np.argmin(dp))
        cost = float(dp[idx])
        path = [idx]
        for b in reversed(backs):
            path.append(int(b[path[-1]]))
        path.reverse()
        result = []
        for k, si in enumerate(path):
            vi, pos, _, free = (a[si] for a in st[k])
            result.append((all_vs[k][int(vi)], None if free else int(pos)))
        self._slices = slices
        return result, cost, dropped


def solve_track(
    notes: list[Note],
    open_midi: list[int],
    capo: int,
    cfg: SolverConfig,
    *,
    max_fret: int = 22,
    open_pref: float = 1.0,
    standard_tuning: bool = False,
    chords_at: dict[int, str] | None = None,
    seconds_at=None,
    tolerance_ticks: int = 0,
    max_notes_per_slice: int | None = None,
    tapping: bool = False,
) -> SolveResult:
    """Assign string/fret/finger to every note. Returns new Note objects."""
    solver = FretSolver(open_midi, capo, max_fret, cfg, open_pref, standard_tuning, tapping)
    work = [n.model_copy(deep=True) for n in notes]
    slices = make_slices(work, tolerance_ticks)
    pre_dropped: list[Note] = []
    limit = min(max_notes_per_slice or solver.n_strings, solver.n_strings)
    for sl in slices:
        if seconds_at:
            sl.seconds = seconds_at(sl.tick)
        if chords_at:
            sl.chord = chords_at.get(sl.tick)
        if len(sl.notes) > limit:
            order = note_priority(sl.notes)
            sl.notes, extra = order[:limit], order[limit:]
            pre_dropped.extend(extra)

    path, cost, dropped = solver.solve(slices)
    out: list[Note] = []
    for sl, (v, pos) in zip(solver._slices if path else [], path, strict=False):
        fr = assign_fingers(v.positions, pos)
        for i, (n, (s, f)) in enumerate(zip(sl.notes, v.positions, strict=True)):
            n.string, n.fret = s, f
            n.techniques = [t for t in n.techniques if t != "tap"]
            if v.tapped:
                n.techniques.append("tap")
                n.finger = None  # played by the picking hand, so no fretting-hand finger
            elif not n.user_edited or n.finger is None:
                n.finger = fr.fingers[i]
            flags = [x for x in n.flags if x not in ("barre", "stretch", "hardFingering")]
            if fr.barre and fr.fingers[i] == 1 and f > 0:
                flags.append("barre")
            if fr.stretch and fr.stretch[i]:
                flags.append("stretch")
            if not fr.feasible:
                flags.append("hardFingering")
            n.flags = flags
            out.append(n)
    out.sort(key=lambda n: (n.tick, -n.midi))
    check_legato(out)
    return SolveResult(notes=out, cost=cost, dropped=pre_dropped + dropped)


LEGATO = ("slide", "hammer", "pull")


def check_legato(notes: list[Note]) -> None:
    """Keep a slide / hammer-on / pull-off only if both notes ended up on the same string at different
    frets; hammer vs pull is set from the fret direction. Otherwise the technique is removed."""
    by_id = {n.id: n for n in notes}
    for n in notes:
        if not n.legato_to:
            continue
        nxt = by_id.get(n.legato_to)
        if nxt is None or nxt.string != n.string or nxt.fret == n.fret or nxt.fret is None or n.fret is None:
            n.techniques = [t for t in n.techniques if t not in LEGATO]
            n.legato_to = None
            n.flags = [f for f in n.flags if f != "suggestedTechnique"]
        else:
            if "slide" not in n.techniques:
                kind = "hammer" if nxt.fret > n.fret else "pull"
                n.techniques = [kind] + [t for t in n.techniques if t not in LEGATO]
            if "tap" in n.techniques or "tap" in nxt.techniques:
                # Tapping is built from hammer-ons and pull-offs, so here they're expected, not a guess.
                n.flags = [f for f in n.flags if f != "suggestedTechnique"]
