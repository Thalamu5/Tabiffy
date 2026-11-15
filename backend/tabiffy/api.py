"""FastAPI app (SPEC section 8)."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from . import __version__, jobs, storage
from .midi_export import score_to_midi
from .models import CapoSuggestion, SolverSettings, TabiffyScore, TargetInstrument, _Model
from .pipeline import ResolveOptions, build_track, relabel_chords, suggest_capo
from .tunings import TUNINGS

MAX_UPLOAD_BYTES = 20 * 1024 * 1024

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
async def create_job(file: UploadFile = File(...)) -> dict:
    filename = file.filename or "upload"
    try:
        jobs.check_file(filename)
    except jobs.UnsupportedFile as e:
        raise HTTPException(415, str(e)) from None
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is too large (20 MB max)")
    if not data:
        raise HTTPException(400, "The file is empty")
    job_id = storage.new_job(filename, data)
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
    new_track.name = score.tracks[idx].name
    score.tracks[idx] = new_track
    relabel_chords(score)
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
