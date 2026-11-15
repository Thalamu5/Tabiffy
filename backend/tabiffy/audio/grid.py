"""Map recording time (seconds) to score ticks using the detected beats.

Every detected beat becomes exactly one quarter note (960 ticks), so the notation follows
the band's tempo drift while the score itself gets one steady tempo. Sync points
(tick -> seconds) let the player follow the original recording.
"""

from __future__ import annotations

import numpy as np

from ..models import SyncPoint
from .beats import BeatInfo


class BeatGrid:
    def __init__(
        self,
        beats: BeatInfo,
        duration: float,
        tpq: int = 960,
        tempo_factor: float = 1.0,
        downbeat_shift: int = 0,
        beats_per_bar: int | None = None,
    ):
        times = np.asarray(beats.beat_times, dtype=float)
        if len(times) < 2:
            step = 60.0 / (beats.bpm or 120.0)
            times = np.arange(0.0, max(duration, step) + step, step)
        down = beats.downbeat_index
        if tempo_factor == 2:
            mids = (times[:-1] + times[1:]) / 2
            times = np.sort(np.concatenate([times, mids]))
            down *= 2
        elif tempo_factor == 0.5:
            times = times[down % 2 :: 2]
            down //= 2
        bpb = beats_per_bar or beats.beats_per_bar
        down = (down + downbeat_shift) % bpb
        step = float(np.median(np.diff(times)))

        # Prepend L beats so that the grid starts at or before 0 s and beat 0 is a downbeat:
        # original beat i is a downbeat when (i - down) % bpb == 0, and it becomes beat i + L.
        # (a first beat within a quarter beat of 0 s counts as starting at 0)
        lead = int(np.ceil(max(0.0, times[0] - 0.25 * step) / step))
        while (lead + down) % bpb != 0:
            lead += 1
        times = np.concatenate([times[0] - step * np.arange(lead, 0, -1), times])
        # Append beats past the end of the recording.
        tail = []
        t = times[-1]
        while t < duration + step:
            t += step
            tail.append(t)
        self.times = np.concatenate([times, np.array(tail)])
        self.tpq = tpq
        self.beats_per_bar = bpb
        self.bpm = round(60.0 / step, 2)

    def tick(self, seconds: float) -> int:
        idx = np.arange(len(self.times)) * self.tpq
        if seconds <= self.times[0]:
            slope = self.tpq / (self.times[1] - self.times[0])
            return round((seconds - self.times[0]) * slope)
        if seconds >= self.times[-1]:
            slope = self.tpq / (self.times[-1] - self.times[-2])
            return round(idx[-1] + (seconds - self.times[-1]) * slope)
        return round(float(np.interp(seconds, self.times, idx)))

    def seconds(self, tick: int) -> float:
        idx = np.arange(len(self.times)) * self.tpq
        return float(np.interp(tick, idx, self.times))

    def sync_points(self) -> list[SyncPoint]:
        return [SyncPoint(tick=k * self.tpq, seconds=round(float(t), 4)) for k, t in enumerate(self.times) if t >= 0]
