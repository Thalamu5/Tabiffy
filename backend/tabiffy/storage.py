"""File-based storage for jobs, intermediate stage outputs and scores.

Layout:  DATA_DIR/jobs/<id>/{job.json, input.<ext>, stages/<stage>.json, score.json}

v0.1 keeps everything on local disk so the app runs with zero infrastructure. The
interface is small on purpose so it can move to Postgres + S3 later (SPEC section 2).
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

from .models import TabiffyScore

_lock = threading.Lock()


def data_dir() -> Path:
    d = Path(os.environ.get("TABIFFY_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _job_dir(job_id: str) -> Path:
    if not job_id or any(c not in "0123456789abcdef" for c in job_id):
        raise KeyError(job_id)
    return data_dir() / "jobs" / job_id


def new_job(filename: str, data: bytes | None = None, options: dict | None = None) -> str:
    """Create a job folder. Pass `data`, or write the upload to `input_path(job_id, filename)` yourself."""
    job_id = uuid.uuid4().hex
    (_job_dir(job_id) / "stages").mkdir(parents=True)
    if data is not None:
        input_path(job_id, filename).write_bytes(data)
    job = {
        "id": job_id,
        "filename": filename,
        "status": "queued",
        "stage": "queued",
        "stageLabel": "Waiting in line",
        "progress": 0.0,
        "error": None,
        "options": options or {},
    }
    write_job(job_id, job)
    return job_id


def input_path(job_id: str, filename: str) -> Path:
    ext = Path(filename).suffix.lower() or ".bin"
    return _job_dir(job_id) / f"input{ext}"


def stages_dir(job_id: str) -> Path:
    return _job_dir(job_id) / "stages"


def audio_preview(score_id: str) -> Path:
    p = stages_dir(score_id) / "audio.mp3"
    if not p.exists():
        raise KeyError(score_id)
    return p


def delete_job_dir(job_id: str) -> None:
    import shutil

    shutil.rmtree(_job_dir(job_id), ignore_errors=True)


def write_job(job_id: str, job: dict) -> None:
    """Save a job's status atomically (write a temp file, then rename)."""
    p = _job_dir(job_id) / "job.json"
    with _lock:
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(job))
        tmp.replace(p)


def read_job(job_id: str) -> dict:
    """Load a job's status; KeyError if it doesn't exist."""
    p = _job_dir(job_id) / "job.json"
    if not p.exists():
        raise KeyError(job_id)
    with _lock:
        return json.loads(p.read_text())


def update_job(job_id: str, **fields) -> dict:
    job = read_job(job_id)
    job.update(fields)
    write_job(job_id, job)
    return job


def input_file(job_id: str) -> Path:
    return next(_job_dir(job_id).glob("input.*"))


def write_stage(job_id: str, stage: str, score: TabiffyScore) -> None:
    (_job_dir(job_id) / "stages" / f"{stage}.json").write_text(score.to_json())


def read_stage(job_id: str, stage: str) -> TabiffyScore:
    p = _job_dir(job_id) / "stages" / f"{stage}.json"
    if not p.exists():
        raise KeyError(job_id)
    return TabiffyScore.model_validate_json(p.read_text())


def write_score(score_id: str, score: TabiffyScore) -> None:
    p = _job_dir(score_id) / "score.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(score.to_json())
    tmp.replace(p)


def read_score(score_id: str) -> TabiffyScore:
    p = _job_dir(score_id) / "score.json"
    if not p.exists():
        raise KeyError(score_id)
    return TabiffyScore.model_validate_json(p.read_text())
