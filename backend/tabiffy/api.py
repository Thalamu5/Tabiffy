"""FastAPI app (SPEC section 8)."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from . import __version__, jobs, storage
from .midi_export import score_to_midi
from .models import CapoSuggestion, SolverSettings, TabiffyScore, TargetInstrument, TuningSuggestion, _Model
from .pipeline import ResolveOptions, build_track, relabel_chords, solve_all, suggest_capo
from .tuning_suggest import suggest_tunings
from .tunings import TUNINGS

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
CHUNK = 1024 * 1024

app = FastAPI(title="Tabiffy API", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("TABIFFY_CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class ResolveRequest(_Model):
    track_id: str
    tuning: list[str] | None = None
    capo: int = Field(0, ge=0, le=12)
    target: TargetInstrument = "guitar"
    transpose: int = Field(0, ge=-12, le=12)
    locked_note_ids: list[str] = Field(default_factory=list)
    settings: SolverSettings | None = None


def _score_or_404(score_id: str) -> TabiffyScore:
    try:
        return storage.read_score(score_id)
    except KeyError:
        raise HTTPException(404, "Score not found") from None


def _resolve_inputs(score_id: str, req: ResolveRequest):
    score = _score_or_404(score_id)
    try:
        source = storage.read_stage(score_id, "1b_source")
    except KeyError:
        raise HTTPException(409, "Source data for this score is missing") from None
    idx = next((i for i, t in enumerate(score.tracks) if t.id == req.track_id), None)
    if idx is None:
        raise HTTPException(404, "Track not found")
    track = score.tracks[idx]
    src_idx = track.source_track_index if track.source_track_index is not None else idx
    if not 0 <= src_idx < len(source.tracks):
        raise HTTPException(409, "Source track is missing")
    locked_ids = set(req.locked_note_ids)
    locked = [n for n in track.notes if n.user_edited or n.id in locked_ids]
    for n in locked:
        n.user_edited = True
    if req.tuning is not None:
        if req.target != "piano" and not 4 <= len(req.tuning) <= 8:
            raise HTTPException(422, "A tuning needs 4-8 strings")
    settings = req.settings or score.settings
    opts = ResolveOptions(
        target=req.target,
        tuning=req.tuning,
        capo=req.capo,
        transpose=req.transpose,
        locked_notes=locked,
        settings=settings,
    )
    return score, source, idx, source.tracks[src_idx], opts


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": __version__}


@app.get("/api/tunings")
def tunings() -> dict:
    return TUNINGS


@app.post("/api/jobs")
async def create_job(
    file: UploadFile = File(...), mode: str = Form("guitar"), tuning: str = Form("auto"), tapping: bool = Form(False)
) -> dict:
    """Upload a MIDI or audio file. `mode` (audio only) says what the recording contains:
    "guitar" | "bass" | "piano" | "vocals" | "other", or "mix" for a whole band mix (rough results).
    `tapping` says the song uses two-hand tapping, so the tab may use tapped notes."""
    filename = file.filename or "upload"
    try:
        kind = jobs.file_kind(filename)
    except jobs.UnsupportedFile as e:
        raise HTTPException(415, str(e)) from None
    if mode not in jobs.AUDIO_MODES:
        raise HTTPException(422, f"mode must be one of {sorted(jobs.AUDIO_MODES)}")
    if tuning != "auto" and TUNINGS.get(tuning, {}).get("instrument") != "guitar":
        raise HTTPException(422, "tuning must be 'auto' or a guitar tuning key from /api/tunings")
    job_id = storage.new_job(filename, options={"mode": mode, "kind": kind, "tuning": tuning, "tapping": tapping})
    size = 0
    with storage.input_path(job_id, filename).open("wb") as out:
        while chunk := await file.read(CHUNK):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                storage.delete_job_dir(job_id)
                raise HTTPException(413, "File is too large (200 MB max)")
            out.write(chunk)
    if size == 0:
        storage.delete_job_dir(job_id)
        raise HTTPException(400, "The file is empty")
    jobs.submit(job_id)
    return {"jobId": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    try:
        return storage.read_job(job_id)
    except KeyError:
        raise HTTPException(404, "Job not found") from None


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    get_job(job_id)

    async def stream():
        last = None
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            job = storage.read_job(job_id)
            if job != last:
                yield f"data: {json.dumps(job)}\n\n"
                last = job
            if job["status"] in ("done", "error"):
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/scores/{score_id}")
def get_score(score_id: str) -> Response:
    score = _score_or_404(score_id)
    return Response(score.to_json(), media_type="application/json")


@app.put("/api/scores/{score_id}")
def put_score(score_id: str, score: TabiffyScore) -> dict:
    _score_or_404(score_id)
    storage.write_score(score_id, score)
    return {"ok": True}


@app.post("/api/scores/{score_id}/resolve")
def resolve(score_id: str, req: ResolveRequest) -> Response:
    """Re-run stages 6-8 (mapping, quantize, solver) for one track."""
    score, source, idx, src_track, opts = _resolve_inputs(score_id, req)
    if req.settings:
        score.settings = req.settings
    new_track, _ = build_track(source, src_track, opts, req.track_id)
    old = score.tracks[idx]
    new_track.name = old.name
    # keep the tuning suggestions; the tuning is now the user's choice unless they kept the detected one
    new_track.tuning_suggestions = old.tuning_suggestions
    new_track.tuning_detected = old.tuning_detected and new_track.tuning == old.tuning
    score.tracks[idx] = new_track
    relabel_chords(score, source)
    storage.write_score(score_id, score)
    return Response(score.to_json(), media_type="application/json")


@app.post("/api/scores/{score_id}/suggest-capo")
def capo_suggestion(score_id: str, req: ResolveRequest) -> CapoSuggestion:
    score, source, idx, src_track, opts = _resolve_inputs(score_id, req)
    if req.target == "piano":
        raise HTTPException(422, "Capo suggestions are for guitar and bass")
    suggestion = suggest_capo(source, src_track, opts)
    score.tracks[idx].capo_suggestion = suggestion
    storage.write_score(score_id, score)
    return suggestion


@app.get("/api/scores/{score_id}/audio")
def score_audio(score_id: str) -> FileResponse:
    """The original recording (as MP3) for audio-transcribed scores."""
    try:
        return FileResponse(storage.audio_preview(score_id), media_type="audio/mpeg")
    except KeyError:
        raise HTTPException(404, "This score has no audio") from None


class TimingRequest(_Model):
    time_signature: tuple[int, int] = (4, 4)
    bpm: float | None = Field(None, ge=20, le=400)  # MIDI scores: set the tempo
    tempo_factor: float = 1.0  # audio scores: 0.5 (half time), 1, or 2 (double time)
    downbeat_shift: int = Field(0, ge=0, le=11)  # audio scores: move bar lines by N beats


@app.post("/api/scores/{score_id}/timing")
def timing(score_id: str, req: TimingRequest) -> Response:
    """Fix the detected tempo / time signature / bar lines and re-solve every track."""
    score = _score_or_404(score_id)
    num, den = req.time_signature
    if not (1 <= num <= 12 and den in (2, 4, 8, 16)):
        raise HTTPException(422, "Unsupported time signature")
    try:
        source = storage.read_stage(score_id, "1b_source")
    except KeyError:
        raise HTTPException(409, "Source data for this score is missing") from None
    if score.audio is not None:
        if den != 4:
            raise HTTPException(422, "For audio, choose a time signature over 4 (e.g. 3/4, 4/4)")
        if req.tempo_factor not in (0.5, 1.0, 2.0):
            raise HTTPException(422, "tempoFactor must be 0.5, 1 or 2")
        from .audio.pipeline import retime

        source, score = retime(storage.stages_dir(score_id), score, req.tempo_factor, req.downbeat_shift % num, num)
    else:
        source.meta.time_signature = (num, den)
        if req.bpm:
            ratio = req.bpm / (source.tempo_map[0].bpm or 120.0)
            for tp in source.tempo_map:
                tp.bpm = round(tp.bpm * ratio, 3)
            source.meta.bpm = source.tempo_map[0].bpm
        score = solve_all(source, score.settings, previous=score)
    storage.write_stage(score_id, "1b_source", source)
    storage.write_score(score_id, score)
    return Response(score.to_json(), media_type="application/json")


class TuningRequest(_Model):
    track_id: str
    strings: list[int] | None = None  # limit to e.g. [7] for 7-string tunings


@app.post("/api/scores/{score_id}/suggest-tuning")
def tuning_suggestion(score_id: str, req: TuningRequest) -> list[TuningSuggestion]:
    """Rank guitar tunings by how well the track's notes fit them."""
    score = _score_or_404(score_id)
    try:
        source = storage.read_stage(score_id, "1b_source")
    except KeyError:
        raise HTTPException(409, "Source data for this score is missing") from None
    idx = next((i for i, t in enumerate(score.tracks) if t.id == req.track_id), None)
    if idx is None:
        raise HTTPException(404, "Track not found")
    track = score.tracks[idx]
    src_idx = track.source_track_index if track.source_track_index is not None else idx
    if not 0 <= src_idx < len(source.tracks):
        raise HTTPException(409, "Source track is missing")
    suggestions = suggest_tunings(source, source.tracks[src_idx], score.settings, set(req.strings or []) or None)
    if not req.strings:
        score.tracks[idx].tuning_suggestions = suggestions
        storage.write_score(score_id, score)
    return suggestions


@app.get("/api/scores/{score_id}/export")
def export(score_id: str, format: str = "mid") -> Response:  # noqa: A002 - matches the SPEC's query param
    score = _score_or_404(score_id)
    name = (score.meta.title or "tabiffy").replace('"', "")
    if format == "mid":
        return Response(
            score_to_midi(score),
            media_type="audio/midi",
            headers={"Content-Disposition": f'attachment; filename="{name}.mid"'},
        )
    if format == "json":
        return Response(
            score.to_json(),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{name}.tabiffy.json"'},
        )
    raise HTTPException(400, "Supported formats: mid, json. Guitar Pro (.gp) and PDF are exported in the browser.")


# Serve the built frontend (production / Docker). In development Vite serves it.
_dist = Path(os.environ.get("TABIFFY_FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if _dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        f = (_dist / path).resolve()
        if path and f.is_file() and _dist.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(_dist / "index.html")
