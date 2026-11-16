"""Hostile input: disguised files, injected names, oversized requests, leaked error details."""

import subprocess
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TABIFFY_DATA_DIR", str(tmp_path))
    from tabiffy.api import app

    return TestClient(app)


def wait(client, job_id):
    for _ in range(200):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError(job)


@pytest.mark.skipif(subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0, reason="needs ffmpeg")
@pytest.mark.parametrize(
    ("name", "body"),
    [
        # An HLS playlist pointing at a local file, renamed to .mp3
        ("song.mp3", b"#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:10,\nfile:///etc/passwd\n#EXT-X-ENDLIST\n"),
        # An ffmpeg concat script, renamed to .wav
        ("song.wav", b"ffconcat version 1.0\nfile '/etc/hostname'\n"),
    ],
)
def test_disguised_playlists_are_refused(client, name, body):
    r = client.post("/api/jobs", files={"file": (name, body, "audio/mpeg")})
    job = wait(client, r.json()["jobId"])
    assert job["status"] == "error" and "/etc" not in job["error"]


def test_tuning_names_are_validated(client, fixtures_dir):
    path = fixtures_dir / "pentatonic_riff.mid"
    job_id = client.post("/api/jobs", files={"file": (path.name, path.read_bytes(), "audio/midi")}).json()["jobId"]
    wait(client, job_id)
    tid = client.get(f"/api/scores/{job_id}").json()["tracks"][0]["id"]
    # Something that would inject extra commands into the score text alphaTab reads.
    evil = ["E2", "A2", "D3", 'G3) \\title "x"', "B3", "E4"]
    assert client.post(f"/api/scores/{job_id}/resolve", json={"trackId": tid, "tuning": evil}).status_code == 422
    score = client.get(f"/api/scores/{job_id}").json()
    score["tracks"][0]["tuning"] = evil
    assert client.put(f"/api/scores/{job_id}", json=score).status_code == 422


def test_export_name_cannot_break_headers(client, fixtures_dir):
    path = fixtures_dir / "pentatonic_riff.mid"
    job_id = client.post("/api/jobs", files={"file": (path.name, path.read_bytes(), "audio/midi")}).json()["jobId"]
    wait(client, job_id)
    score = client.get(f"/api/scores/{job_id}").json()
    score["meta"]["title"] = 'evil"\r\nSet-Cookie: x=1'
    assert client.put(f"/api/scores/{job_id}", json=score).status_code == 200
    r = client.get(f"/api/scores/{job_id}/export?format=mid")
    assert r.status_code == 200 and "set-cookie" not in r.headers
    assert r.headers["content-disposition"] == 'attachment; filename="evilSet-Cookie x1.mid"'


def test_oversized_json_is_refused(client):
    r = client.put(
        "/api/scores/abc",
        content=b"{}",
        headers={"content-type": "application/json", "content-length": str(50 * 1024 * 1024)},
    )
    assert r.status_code == 413


def test_unexpected_errors_do_not_leak_details(client, monkeypatch, fixtures_dir):
    from tabiffy import jobs

    def boom(*a, **k):
        raise RuntimeError("secret internal path /srv/tabiffy/data")

    monkeypatch.setattr(jobs, "import_midi", boom)
    path = fixtures_dir / "pentatonic_riff.mid"
    job = wait(
        client, client.post("/api/jobs", files={"file": (path.name, path.read_bytes(), "audio/midi")}).json()["jobId"]
    )
    assert job["status"] == "error" and "secret" not in job["error"] and "/srv" not in job["error"]


def test_path_tricks_never_reach_files(client):
    for path in ["/api/scores/..%2F..%2Fetc%2Fpasswd", "/api/jobs/../../etc/passwd", "/..%2F..%2Fetc%2Fpasswd"]:
        r = client.get(path)
        assert "root:" not in r.text and r.status_code in (200, 404)  # 200 = the app's own page


def test_unwritable_data_folder_gives_a_clear_message(client, monkeypatch, fixtures_dir):
    from tabiffy import storage

    def denied(*a, **k):
        raise PermissionError("denied")

    monkeypatch.setattr(storage, "new_job", denied)
    path = fixtures_dir / "pentatonic_riff.mid"
    r = client.post("/api/jobs", files={"file": (path.name, path.read_bytes(), "audio/midi")})
    assert r.status_code == 503 and "data folder" in r.json()["detail"]
