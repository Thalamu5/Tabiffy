"""Tick <-> seconds conversion using a tempo map."""

from __future__ import annotations

from bisect import bisect_right

from .models import TempoPoint


class TempoMap:
    def __init__(self, points: list[TempoPoint], tpq: int):
        pts = sorted(points, key=lambda p: p.tick) or [TempoPoint(tick=0, bpm=120)]
        if pts[0].tick != 0:
            pts.insert(0, TempoPoint(tick=0, bpm=pts[0].bpm))
        self.ticks = [p.tick for p in pts]
        self.bpms = [p.bpm for p in pts]
        self.tpq = tpq
        self.secs = [0.0]
        for i in range(1, len(pts)):
            self.secs.append(self.secs[-1] + self._dur(self.ticks[i] - self.ticks[i - 1], self.bpms[i - 1]))

    def _dur(self, ticks: int, bpm: float) -> float:
        return ticks / self.tpq * 60.0 / bpm

    def seconds(self, tick: int) -> float:
        i = bisect_right(self.ticks, tick) - 1
        return self.secs[i] + self._dur(tick - self.ticks[i], self.bpms[i])

    def ticks_for_seconds_at(self, tick: int, seconds: float) -> int:
        i = bisect_right(self.ticks, tick) - 1
        return round(seconds * self.bpms[i] / 60.0 * self.tpq)
