"""Background jobs.

If TABIFFY_REDIS_URL is set, jobs go to an RQ queue named "tabiffy" and a separate worker
process runs them (`rq worker tabiffy --url $TABIFFY_REDIS_URL`, see docker-compose.yml).
Otherwise they run in an in-process thread pool, which is fine for development.
Both share the data directory, where `job.json` holds status and progress.
"""

from __future__ import annotations

import logging
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import storage
from .pipeline import import_midi

log = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tabiffy-job")

MIDI_EXTS = {".mid", ".midi", ".smf"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus", ".aiff", ".aif"}
AUDIO_MODES = {"full", "guitar", "bass", "piano", "other"}
JOB_TIMEOUT_SECONDS = 60 * 60

STAGE_LABELS = {
    "queued": "Waiting in line",
    "decode": "Reading the file",
    "analyze": "Analyzing",
    "separate": "Separating the instruments",
    "beats": "Finding the beat",
    "solve": "Working out fingerings",
    "chords": "Naming chords",
}


class UnsupportedFile(ValueError):
    pass


def file_kind(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in MIDI_EXTS:
        return "midi"
    if ext in AUDIO_EXTS:
        return "audio"
    raise UnsupportedFile(
        f"Unsupported file type {ext or '(none)'}. Upload a MIDI file (.mid) or audio (.mp3, .wav, .flac, .ogg, .m4a)."
    )


def check_file(filename: str) -> None:
    file_kind(filename)


def stage_label(stage: str) -> str:
    if stage.startswith("transcribe:"):
        part = stage.split(":", 1)[1]
        return f"Listening for notes: {part}"
    return STAGE_LABELS.get(stage, stage)


def run_job(job_id: str) -> None:
    def on_stage(stage: str, progress: float) -> None:
        storage.update_job(
            job_id, status="running", stage=stage, stageLabel=stage_label(stage), progress=round(progress, 3)
        )

    try:
        job = storage.read_job(job_id)
        path = storage.input_file(job_id)
        if file_kind(job["filename"]) == "midi":
            source, score = import_midi(path.read_bytes(), job["filename"], on_stage=on_stage)
        else:
            from .audio.decode import AudioError
            from .audio.pipeline import import_audio

            mode = job.get("options", {}).get("mode", "full")
            try:
                source, score = import_audio(path, storage.stages_dir(job_id), job["filename"], mode, on_stage=on_stage)
            except AudioError as e:
                raise UnsupportedFile(str(e)) from None
        storage.write_stage(job_id, "1b_source", source)
        storage.write_score(job_id, score)
        storage.update_job(job_id, status="done", stage="done", stageLabel="Done", progress=1.0, scoreId=job_id)
    except UnsupportedFile as e:
        storage.update_job(job_id, status="error", error=str(e))
    except Exception as e:  # noqa: BLE001 - surface any failure to the user
        log.error("job %s failed: %s", job_id, traceback.format_exc())
        msg = "Audio support isn't installed on this server" if isinstance(e, ImportError) else str(e)
        storage.update_job(job_id, status="error", error=msg or e.__class__.__name__)


def _queue():
    url = os.environ.get("TABIFFY_REDIS_URL")
    if not url:
        return None
    from redis import Redis
    from rq import Queue

    return Queue("tabiffy", connection=Redis.from_url(url))


def submit(job_id: str) -> None:
    q = _queue()
    if q is not None:
        q.enqueue(run_job, job_id, job_timeout=JOB_TIMEOUT_SECONDS, result_ttl=3600, failure_ttl=86400)
    else:
        _executor.submit(run_job, job_id)
