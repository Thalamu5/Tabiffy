"""Audio pipeline tests on synthesized recordings with known notes.

Demucs itself isn't run here (its weights are an ~80 MB download); a stand-in returns the
true instrument parts, so everything around it is tested for real.
"""

import shutil
import time

import numpy as np
import pytest
from audio_synth import band, write

pytest.importorskip("librosa")
pytest.importorskip("basic_pitch")

from tabiffy.audio import separate as sep  # noqa: E402
from tabiffy.audio.beats import BeatInfo, detect_beats, meter_and_downbeat  # noqa: E402
from tabiffy.audio.grid import BeatGrid  # noqa: E402
from tabiffy.audio.pipeline import import_audio, retime  # noqa: E402
from tabiffy.audio.transcribe import RawNote, keep_one_line, transcribe  # noqa: E402


@pytest.fixture(scope="module")
def recording(tmp_path_factory):
    d = tmp_path_factory.mktemp("rec")
    stems, truth = band(bpm=100, bars=8)
    paths = {k: write(d / f"true_{k}.wav", v) for k, v in stems.items()}
    mix = write(d / "song.wav", sum(stems.values()))
    return {"dir": d, "stems": paths, "mix": mix, "truth": truth}


@pytest.fixture
def fake_demucs(monkeypatch, recording):
    def fake(wav, out_dir, on_progress=None):
        out_dir.mkdir(parents=True, exist_ok=True)
        out = {}
        for k, v in recording["stems"].items():
            out[k] = out_dir / f"{k}.wav"
            shutil.copy(v, out[k])
        return out

    monkeypatch.setattr(sep, "separate", fake)


# --- beat grid -------------------------------------------------------------------
def test_grid_maps_beats_to_quarter_notes():
    beats = BeatInfo(bpm=120, beat_times=[0.5 * i for i in range(16)], beats_per_bar=4, downbeat_index=0)
    g = BeatGrid(beats, duration=8.0)
    assert g.tick(0.0) == 0 and g.tick(0.5) == 960 and g.tick(0.75) == 1440
    assert g.seconds(1920) == pytest.approx(1.0)
    assert g.bpm == 120


def test_grid_starts_on_a_downbeat():
    # first detected downbeat is the 2nd beat (index 1) at 1.0 s -> one pickup beat before it
    beats = BeatInfo(bpm=120, beat_times=[0.5 + 0.5 * i for i in range(16)], beats_per_bar=4, downbeat_index=1)
    g = BeatGrid(beats, duration=8.0)
    assert g.tick(1.0) % (4 * 960) == 0
    assert g.tick(0.0) >= 0


def test_grid_half_and_double_time():
    beats = BeatInfo(bpm=120, beat_times=[0.5 * i for i in range(16)], beats_per_bar=4, downbeat_index=0)
    assert BeatGrid(beats, 8.0, tempo_factor=2).tick(0.5) == 1920
    assert BeatGrid(beats, 8.0, tempo_factor=0.5).tick(1.0) == 960
    assert BeatGrid(beats, 8.0, tempo_factor=2).bpm == 240


def test_grid_downbeat_shift_moves_bar_lines():
    beats = BeatInfo(bpm=120, beat_times=[0.5 * i for i in range(16)], beats_per_bar=4, downbeat_index=0)
    g = BeatGrid(beats, 8.0, downbeat_shift=1)
    assert g.tick(0.5) % 3840 == 0


def test_sync_points_follow_the_beats():
    beats = BeatInfo(bpm=120, beat_times=[0.5 * i for i in range(8)], beats_per_bar=4, downbeat_index=0)
    pts = BeatGrid(beats, 4.0).sync_points()
    assert pts[0].tick == 0 and pts[0].seconds == 0
    assert pts[2].tick == 1920 and pts[2].seconds == pytest.approx(1.0)


def test_meter_detection():
    four = np.tile([3.0, 1.0, 1.5, 1.0], 8)
    assert meter_and_downbeat(four) == (4, 0)
    three = np.tile([1.0, 3.0, 1.0], 8)
    assert meter_and_downbeat(three) == (3, 1)


def test_confidence_heuristic():
    from tabiffy.audio.transcribe import confidence

    assert confidence(0.8, 0.5) == 1.0
    assert confidence(0.2, 0.5) < 0.5  # quiet
    assert confidence(0.8, 0.02) < 0.5  # very short
    assert 0 <= confidence(0.0, 0.0) <= confidence(0.4, 0.3) <= 1


def test_keep_one_line():
    notes = [RawNote(0.0, 1.0, 60, 0.5), RawNote(0.0, 1.0, 64, 0.5), RawNote(0.5, 1.0, 62, 0.5)]
    top = keep_one_line(notes, "top")
    assert [n.pitch for n in top] == [64, 62]
    assert [n.pitch for n in keep_one_line(notes, "bottom")] == [60, 62]


# --- real models on synthesized audio -----------------------------------------------------
def test_basic_pitch_transcribes_guitar_stem(recording):
    import mir_eval

    notes = transcribe(recording["stems"]["guitar"], "guitar")
    truth = recording["truth"]
    hz = lambda m: 440.0 * 2 ** ((m - 69) / 12)  # noqa: E731
    _, _, f1, _ = mir_eval.transcription.precision_recall_f1_overlap(
        np.array([[s, e] for s, e, _ in truth]),
        np.array([hz(m) for *_, m in truth]),
        np.array([[n.start, n.end] for n in notes]),
        np.array([hz(n.pitch) for n in notes]),
        offset_ratio=None,
    )
    assert f1 > 0.7


def test_beat_tracking(recording):
    b = detect_beats(recording["mix"])
    assert b.bpm == pytest.approx(100, rel=0.03)
    assert b.beats_per_bar == 4
    assert b.beat_times[b.downbeat_index] < 0.2  # the first downbeat is the start of the song


def test_full_song_pipeline(tmp_path, recording, fake_demucs):
    start = time.perf_counter()
    stages = []
    source, score = import_audio(
        recording["mix"], tmp_path / "work", "my_song.wav", "full", on_stage=lambda s, p: stages.append(s)
    )
    assert time.perf_counter() - start < 60
    assert stages[0] == "decode" and "separate" in stages and "beats" in stages
    assert [t.name for t in score.tracks] == ["Guitar", "Bass"]
    assert score.tracks[1].target_instrument == "bass"
    assert tuple(score.meta.time_signature) == (4, 4)
    assert score.meta.key == "C major"
    assert [c.symbol for c in score.chords][:4] == ["C", "G", "Am", "F"]
    gtr = score.tracks[0]
    assert all(n.string and n.fret is not None and 0 <= n.confidence <= 1 for n in gtr.notes)
    assert score.audio and score.audio.separated and score.audio.sync_points
    assert (tmp_path / "work" / "audio.mp3").exists()
    assert not (tmp_path / "work" / "decoded.wav").exists()  # big intermediates are cleaned up

    # half time: same notes, half as many beats
    _, slow = retime(tmp_path / "work", score, 0.5, 0, 4)
    assert slow.audio.tempo_factor == 0.5
    assert slow.meta.bpm == pytest.approx(score.meta.bpm / 2, rel=0.02)
    assert len(slow.tracks[0].notes) > 0.8 * len(gtr.notes)


def test_solo_mode_skips_separation(tmp_path, recording, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("separation should not run for solo recordings")

    monkeypatch.setattr(sep, "separate", boom)
    _, score = import_audio(recording["stems"]["guitar"], tmp_path / "w", "solo.wav", "guitar")
    assert [t.name for t in score.tracks] == ["Guitar"]
    assert score.audio.separated is False


def test_falls_back_to_full_mix_without_demucs(tmp_path, recording, monkeypatch):
    def unavailable(*a, **k):
        raise sep.SeparationUnavailable("no weights")

    monkeypatch.setattr(sep, "separate", unavailable)
    _, score = import_audio(recording["mix"], tmp_path / "w", "song.wav", "full")
    assert [t.name for t in score.tracks] == ["Full mix"]
    assert score.audio.warnings


def test_rejects_non_audio(tmp_path):
    from tabiffy.audio.decode import AudioError, decode

    bad = tmp_path / "fake.mp3"
    bad.write_bytes(b"not audio at all")
    with pytest.raises(AudioError):
        decode(bad, tmp_path / "out.wav")


def test_demucs_wrapper_writes_stems(tmp_path, recording, monkeypatch):
    """The tensor plumbing around Demucs, with a stand-in model."""
    torch = pytest.importorskip("torch")
    pytest.importorskip("demucs")
    import demucs.apply

    class FakeModel:
        samplerate = 44100
        sources = ["drums", "bass", "other", "vocals", "guitar", "piano"]

    def fake_apply(model, mix, **kw):
        kw["callback"]({"segment_offset": mix.shape[-1] - 1})
        return torch.stack([mix[0] * (i + 1) / 10 for i in range(len(model.sources))])[None]

    monkeypatch.setattr(sep, "_model", FakeModel())
    monkeypatch.setattr(demucs.apply, "apply_model", fake_apply)
    progress = []
    stems = sep.separate(recording["mix"], tmp_path / "stems", progress.append)
    assert set(stems) == set(FakeModel.sources)
    assert all(p.exists() for p in stems.values())
    assert progress and progress[-1] == pytest.approx(1.0)


# --- API ---------------------------------------------------------------------
def test_audio_upload_through_the_api(tmp_path, monkeypatch, recording, fake_demucs):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("TABIFFY_DATA_DIR", str(tmp_path))
    from tabiffy.api import app

    client = TestClient(app)
    r = client.post(
        "/api/jobs", files={"file": ("song.wav", recording["mix"].read_bytes(), "audio/wav")}, data={"mode": "full"}
    )
    assert r.status_code == 200, r.text
    job_id = r.json()["jobId"]
    for _ in range(600):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert job["status"] == "done", job
    score = client.get(f"/api/scores/{job_id}").json()
    assert score["audio"]["syncPoints"] and score["audio"]["separated"]
    audio = client.get(f"/api/scores/{job_id}/audio")
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mpeg"

    r = client.post(
        f"/api/scores/{job_id}/timing", json={"timeSignature": [3, 4], "tempoFactor": 1, "downbeatShift": 0}
    )
    assert r.status_code == 200, r.text
    assert r.json()["meta"]["timeSignature"] == [3, 4]
    bad = client.post(f"/api/scores/{job_id}/timing", json={"timeSignature": [6, 8]})
    assert bad.status_code == 422
