import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TABIFFY_DATA_DIR", str(tmp_path))
    from tabiffy.api import app

    return TestClient(app)


def upload(client, path):
    r = client.post("/api/jobs", files={"file": (path.name, path.read_bytes(), "audio/midi")})
    assert r.status_code == 200, r.text
    job_id = r.json()["jobId"]
    for _ in range(100):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    return job_id


def test_midi_upload_to_score(client, fixtures_dir):
    sid = upload(client, fixtures_dir / "chord_progression.mid")
    score = client.get(f"/api/scores/{sid}").json()
    assert score["version"] == 1 and score["ticksPerQuarter"] == 960
    t = score["tracks"][0]
    assert t["targetInstrument"] == "guitar" and t["tuning"][0] == "E2"
    assert all("string" in n and "fret" in n and "finger" in n for n in t["notes"])
    assert [c["symbol"] for c in score["chords"]][:4] == ["C", "G", "Am", "F"]


def test_resolve_with_new_tuning_and_capo(client, fixtures_dir):
    sid = upload(client, fixtures_dir / "pentatonic_riff.mid")
    score = client.get(f"/api/scores/{sid}").json()
    tid = score["tracks"][0]["id"]
    locked = score["tracks"][0]["notes"][0]
    r = client.post(
        f"/api/scores/{sid}/resolve",
        json={
            "trackId": tid,
            "tuning": ["D2", "A2", "D3", "G3", "B3", "E4"],
            "capo": 2,
            "lockedNoteIds": [locked["id"]],
        },
    )
    assert r.status_code == 200, r.text
    t = r.json()["tracks"][0]
    assert t["capo"] == 2 and t["tuning"][0] == "D2"
    kept = next(n for n in t["notes"] if n["id"] == locked["id"])
    assert (kept["string"], kept["fret"]) == (locked["string"], locked["fret"])
    assert kept["userEdited"] is True


def test_resolve_to_piano_and_transpose(client, fixtures_dir):
    sid = upload(client, fixtures_dir / "piano_two_hands.mid")
    score = client.get(f"/api/scores/{sid}").json()
    tid = score["tracks"][0]["id"]
    before = [n["midi"] for n in score["tracks"][0]["notes"]]
    r = client.post(f"/api/scores/{sid}/resolve", json={"trackId": tid, "target": "piano", "transpose": 2})
    t = r.json()["tracks"][0]
    assert t["targetInstrument"] == "piano"
    assert all(n["hand"] in ("L", "R") and "string" not in n for n in t["notes"])
    assert min(n["midi"] for n in t["notes"]) >= min(before)


def test_capo_suggestion(client, fixtures_dir):
    sid = upload(client, fixtures_dir / "chord_progression.mid")
    tid = client.get(f"/api/scores/{sid}").json()["tracks"][0]["id"]
    r = client.post(f"/api/scores/{sid}/suggest-capo", json={"trackId": tid})
    assert r.status_code == 200
    assert 0 <= r.json()["capo"] <= 7


def test_save_and_export(client, fixtures_dir):
    sid = upload(client, fixtures_dir / "bass_line.mid")
    score = client.get(f"/api/scores/{sid}").json()
    score["meta"]["title"] = "Edited"
    assert client.put(f"/api/scores/{sid}", json=score).status_code == 200
    assert client.get(f"/api/scores/{sid}").json()["meta"]["title"] == "Edited"
    mid = client.get(f"/api/scores/{sid}/export?format=mid")
    assert mid.status_code == 200 and mid.content[:4] == b"MThd"


def test_rejects_unknown_file_types(client):
    r = client.post("/api/jobs", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 415
    assert "MIDI" in r.json()["detail"]


def test_rejects_bad_mode(client, fixtures_dir):
    path = fixtures_dir / "bass_line.mid"
    r = client.post("/api/jobs", files={"file": (path.name, path.read_bytes())}, data={"mode": "kazoo"})
    assert r.status_code == 422


def test_midi_timing_override(client, fixtures_dir):
    sid = upload(client, fixtures_dir / "chord_progression.mid")
    before = client.get(f"/api/scores/{sid}").json()
    r = client.post(f"/api/scores/{sid}/timing", json={"timeSignature": [3, 4], "bpm": 120})
    assert r.status_code == 200, r.text
    score = r.json()
    assert score["meta"]["timeSignature"] == [3, 4]
    assert score["tempoMap"][0]["bpm"] == 120
    assert len(score["tracks"][0]["notes"]) == len(before["tracks"][0]["notes"])
    assert client.get(f"/api/scores/{sid}/audio").status_code == 404


def test_bad_ids_are_404(client):
    assert client.get("/api/scores/..%2F..%2Fetc").status_code == 404
    assert client.get("/api/does-not-exist").status_code == 404
    assert client.get("/api/jobs/nothex").status_code == 404
