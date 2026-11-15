"""Stage 2: stem separation with Demucs (htdemucs_6s: drums, bass, other, vocals, guitar, piano).

The model weights (~80 MB) download on first use from Meta's servers and are cached in
~/.cache/torch. Runs on CPU (a few minutes per song) or on a GPU if torch sees one.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

MODEL_NAME = os.environ.get("TABIFFY_DEMUCS_MODEL", "htdemucs_6s")
_model = None


class SeparationUnavailable(RuntimeError):
    """Demucs (or its weights) isn't available; the caller falls back to the full mix."""


def load_model():
    global _model
    if _model is None:
        try:
            import torch  # noqa: F401
            from demucs.pretrained import get_model
        except ImportError as e:
            raise SeparationUnavailable("Demucs is not installed") from e
        try:
            _model = get_model(MODEL_NAME)
        except Exception as e:  # network errors, missing weights...
            raise SeparationUnavailable(f"Could not load the Demucs model ({e.__class__.__name__})") from e
        _model.eval()
    return _model


def separate(wav_path: Path, out_dir: Path, on_progress: Callable[[float], None] | None = None) -> dict[str, Path]:
    """Split `wav_path` into stems. Returns {stem name: wav path}."""
    import numpy as np
    import soundfile as sf
    import torch
    from demucs.apply import apply_model

    model = load_model()
    audio, sr = sf.read(str(wav_path), dtype="float32", always_2d=True)
    if sr != model.samplerate:
        import librosa

        audio = librosa.resample(audio.T, orig_sr=sr, target_sr=model.samplerate).T
        sr = model.samplerate
    wav = torch.from_numpy(np.ascontiguousarray(audio.T))
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    wav = (wav - mean) / std

    total = wav.shape[-1]

    def callback(info: dict) -> None:
        if on_progress and total:
            on_progress(min(1.0, (info.get("segment_offset", 0) + 1) / total))

    torch.set_num_threads(max(1, os.cpu_count() or 1))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    with torch.no_grad():
        sources = apply_model(
            model, wav[None], device=device, split=True, overlap=0.25, progress=False, callback=callback
        )[0]
    sources = sources * std + mean
    out_dir.mkdir(parents=True, exist_ok=True)
    stems: dict[str, Path] = {}
    for name, src in zip(model.sources, sources, strict=True):
        p = out_dir / f"{name}.wav"
        sf.write(str(p), src.cpu().numpy().T, sr, subtype="PCM_16")
        stems[name] = p
    return stems
