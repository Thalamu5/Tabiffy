"""Stage 1: decode & normalize any audio file with ffmpeg."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

SAMPLE_RATE = 44100
MAX_SECONDS = 15 * 60


class AudioError(ValueError):
    """A problem with the user's file (shown to the user)."""


def _ffmpeg(name: str) -> str:
    exe = shutil.which(name)
    if not exe:
        raise RuntimeError(f"{name} is not installed; it is needed to read audio files")
    return exe


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        [_ffmpeg("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return float(json.loads(out.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        raise AudioError("This file doesn't look like an audio file we can read") from None


def decode(path: Path, out_wav: Path, preview_mp3: Path | None = None) -> float:
    """Convert to 44.1 kHz stereo 16-bit WAV (+ an MP3 for in-browser playback).

    Returns the duration in seconds. Rejects files over 15 minutes.
    """
    duration = probe_duration(path)
    if duration <= 0.5:
        raise AudioError("The audio file is empty or too short")
    if duration > MAX_SECONDS:
        raise AudioError(f"The recording is {duration / 60:.0f} minutes long; the limit is 15 minutes")
    cmd = [
        _ffmpeg("ffmpeg"),
        "-v",
        "error",
        "-y",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "2",
        "-ar",
        str(SAMPLE_RATE),
        "-c:a",
        "pcm_s16le",
        str(out_wav),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise AudioError("Could not decode this audio file") from None
    if preview_mp3 is not None:
        subprocess.run(
            [
                _ffmpeg("ffmpeg"),
                "-v",
                "error",
                "-y",
                "-i",
                str(out_wav),
                "-c:a",
                "libmp3lame",
                "-b:a",
                "160k",
                str(preview_mp3),
            ],
            capture_output=True,
            check=True,
        )
    return duration
