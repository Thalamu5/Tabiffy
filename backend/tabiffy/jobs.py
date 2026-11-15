"""Background job runner.

v0.1 runs jobs in an in-process thread pool: MIDI files take well under a second.
When audio transcription lands (M2/M3) this swaps for RQ/Celery + Redis workers;
`run_job` is already a plain function that a worker can call.
"""

from __future__ import annotations

import logging
import traceback
from concurrent.futures import ThreadPoolExecutor

from . import storage
from .pipeline import import_midi

log = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tabiffy-job")

MIDI_EXTS = {".mid", ".midi", ".smf"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"}


class UnsupportedFile(ValueError):
    pass


def check_file(filename: str) -> None:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in AUDIO_EXTS:
        raise UnsupportedFile(
            "Audio transcription is coming in the next milestone (M2). Tabiffy v0.1 accepts MIDI files "
            "(.mid/.midi) only."
        )
    if ext not in MIDI_EXTS:
        raise UnsupportedFile(f"Unsupported file type {ext or '(none)'}. Please upload a .mid or .midi file.")


def run_job(job_id: str) -> None:
    def on_stage(stage: str, progress: float) -> None:
        storage.update_job(job_id, status="running", stage=stage, progress=round(progress, 2))

    try:
        job = storage.read_job(job_id)
        data = storage.input_file(job_id).read_bytes()
        source, score = import_midi(data, job["filename"], on_stage=on_stage)
        storage.write_stage(job_id, "1b_source", source)
        storage.write_score(job_id, score)
        storage.update_job(job_id, status="done", stage="done", progress=1.0, scoreId=job_id)
    except Exception as e:  # noqa: BLE001 - surface any failure to the user
        log.error("job %s failed: %s", job_id, traceback.format_exc())
        storage.update_job(job_id, status="error", error=str(e) or e.__class__.__name__)


def submit(job_id: str) -> None:
    _executor.submit(run_job, job_id)
