"""Stage 1: decode & normalize any audio file with ffmpeg."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

SAMPLE_RATE = 44100
MAX_SECONDS = 15 * 60
PROBE_TIMEOUT = 60  # seconds; a normal file is probed in well under a second
DECODE_TIMEOUT = 10 * 60  # seconds; a 15-minute file decodes in well under a minute

# Security: ffmpeg detects the format from a file's contents, not its name. Playlist-style formats
# (HLS, concat, ...) can make it read other files or fetch URLs, so only these audio demuxers are
# allowed and only the uploaded file itself may be opened.
SAFE_INPUT = [
    "-protocol_whitelist",
    "file",
    "-format_whitelist",
    "mp3,wav,flac,ogg,aac,aiff,caf,w64,wv,matroska,webm,mov,mp4,m4a,3gp,3g2,mj2",
]


class AudioError(ValueError):
    """A problem with the user's file (shown to the user)."""


def _ffmpeg(name: str) -> str:
    exe = shutil.which(name)
    if not exe:
        raise RuntimeError(f"{name} is not installed; it is needed to read audio files")
    return exe


def probe_duration(path: Path) -> float:
    """Length of an audio file in seconds, read safely with ffprobe; AudioError if it isn't audio."""
    try:
        out = subprocess.run(
            [
                _ffmpeg("ffprobe"),
                "-v",
                "error",
                *SAFE_INPUT,
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=PROBE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise AudioError("This file took too long to read") from None
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
        "-nostdin",
        "-v",
        "error",
        "-y",
        *SAFE_INPUT,
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
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=DECODE_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise AudioError("This file took too long to decode") from None
    if res.returncode != 0:
        raise AudioError("Could not decode this audio file") from None
    if preview_mp3 is not None:
        subprocess.run(
            [
                _ffmpeg("ffmpeg"),
                "-nostdin",
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
            timeout=DECODE_TIMEOUT,
        )
    return duration
