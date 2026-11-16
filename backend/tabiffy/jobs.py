"""Background jobs: an RQ/Redis queue when TABIFFY_REDIS_URL is set (Docker runs a separate worker),
otherwise an in-process thread pool for development. Status and progress live in each job's job.json."""

from __future__ import annotations

import logging
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import storage
from .models import SolverSettings
from .pipeline import import_midi

log = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tabiffy-job")

MIDI_EXTS = {".mid", ".midi", ".smf"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus", ".aiff", ".aif"}
AUDIO_MODES = {"guitar", "bass", "piano", "vocals", "other", "mix"}
JOB_TIMEOUT_SECONDS = 60 * 60

STAGE_LABELS = {
    "queued": "Waiting in line",
    "decode": "Reading the file",
    "analyze": "Analyzing",
    "transcribe": "Listening for notes",
    "beats": "Finding the beat",
    "solve": "Working out fingerings",
    "chords": "Naming chords",
}


class UnsupportedFile(ValueError):
    pass


def file_kind(filename: str) -> str:
    """ "midi" or "audio" from the file extension; UnsupportedFile for anything else."""
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
    return STAGE_LABELS.get(stage, stage)


def run_job(job_id: str) -> None:
    """Process one upload end to end and record progress, the result or a user-friendly error."""

    def on_stage(stage: str, progress: float) -> None:
        storage.update_job(
            job_id, status="running", stage=stage, stageLabel=stage_label(stage), progress=round(progress, 3)
        )

    try:
        job = storage.read_job(job_id)
        path = storage.input_file(job_id)
        options = job.get("options", {})
        tuning = options.get("tuning", "auto")
        settings = SolverSettings(tapping=bool(options.get("tapping", False)))
        if file_kind(job["filename"]) == "midi":
            source, score = import_midi(path.read_bytes(), job["filename"], settings, on_stage=on_stage, tuning=tuning)
        else:
            from .audio.decode import AudioError
            from .audio.pipeline import import_audio

            mode = options.get("mode", "guitar")
            try:
                source, score = import_audio(
                    path, storage.stages_dir(job_id), job["filename"], mode, settings, on_stage=on_stage, tuning=tuning
                )
            except AudioError as e:
                raise UnsupportedFile(str(e)) from None
        storage.write_stage(job_id, "1b_source", source)
        storage.write_score(job_id, score)
        storage.update_job(job_id, status="done", stage="done", stageLabel="Done", progress=1.0, scoreId=job_id)
    except UnsupportedFile as e:
        storage.update_job(job_id, status="error", error=str(e))
    except Exception as e:  # noqa: BLE001 - any failure must end the job, not leave it "running"
        # Details go to the server log only; the user gets a plain message without internal paths or code.
        log.error("job %s failed: %s", job_id, traceback.format_exc())
        msg = (
            "Audio support isn't installed on this server"
            if isinstance(e, ImportError)
            else "Something went wrong while processing this file. Please try again or try another file."
        )
        storage.update_job(job_id, status="error", error=msg)


def _queue():
    """The Redis queue when TABIFFY_REDIS_URL is set, otherwise None (use the thread pool)."""
    url = os.environ.get("TABIFFY_REDIS_URL")
    if not url:
        return None
    from redis import Redis
    from rq import Queue

    return Queue("tabiffy", connection=Redis.from_url(url))


def submit(job_id: str) -> None:
    """Start a job in the background (Redis worker or local thread)."""
    q = _queue()
    if q is not None:
        q.enqueue(run_job, job_id, job_timeout=JOB_TIMEOUT_SECONDS, result_ttl=3600, failure_ttl=86400)
    else:
        _executor.submit(run_job, job_id)
