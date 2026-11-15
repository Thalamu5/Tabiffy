import random
import time

from tabiffy.models import Note, TabiffyScore, Track
from tabiffy.pipeline import ResolveOptions, build_track


def test_resolve_a_long_song_is_fast():
    """SPEC section 3: re-running stages 6-8 should take < 2 s. ~4 minutes of 8ths with chords."""
    rng = random.Random(7)
    notes, tick, i = [], 0, 0
    shapes = [[48, 52, 55, 60, 64], [43, 47, 50, 55, 59, 67], [45, 52, 57, 60, 64], [41, 48, 53, 57, 60, 65]]
    while tick < 960 * 4 * 120:  # 120 bars
        if tick % 1920 == 0:
            for m in shapes[(tick // 3840) % 4]:
                notes.append(Note(id=f"n{i}", tick=tick, duration_ticks=480, midi=m))
                i += 1
        else:
            notes.append(Note(id=f"n{i}", tick=tick, duration_ticks=480, midi=rng.randint(52, 79)))
            i += 1
        tick += 480
    score = TabiffyScore(tracks=[Track(id="s", name="s", source_instrument="guitar", notes=notes)])
    start = time.perf_counter()
    track, _ = build_track(score, score.tracks[0], ResolveOptions(), "t1")
    elapsed = time.perf_counter() - start
    assert len(track.notes) > 1000
    assert elapsed < 2.0, f"took {elapsed:.2f}s"
