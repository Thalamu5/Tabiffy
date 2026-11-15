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


def new_job(filename: str, data: bytes) -> str:
    job_id = uuid.uuid4().hex
    d = _job_dir(job_id)
    (d / "stages").mkdir(parents=True)
    ext = Path(filename).suffix.lower() or ".bin"
    (d / f"input{ext}").write_bytes(data)
    write_job(
        job_id,
        {"id": job_id, "filename": filename, "status": "queued", "stage": "queued", "progress": 0.0, "error": None},
    )
    return job_id


def write_job(job_id: str, job: dict) -> None:
    p = _job_dir(job_id) / "job.json"
    with _lock:
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(job))
        tmp.replace(p)


def read_job(job_id: str) -> dict:
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
