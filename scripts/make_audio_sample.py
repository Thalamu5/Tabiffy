"""Render the self-made "band" demo recording used as an in-app sample.

Run from the repo root:  python scripts/make_audio_sample.py
Writes frontend/public/samples/demo_band.mp3 (plucked-string guitar chords, bass, kick; 100 BPM).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "tests"))

from audio_synth import band, write  # noqa: E402


def main() -> None:
    stems, _ = band(bpm=100, bars=12, seed=3)
    out = ROOT / "frontend" / "public" / "samples" / "demo_band.mp3"
    with tempfile.TemporaryDirectory() as d:
        wav = write(Path(d) / "demo.wav", stems["guitar"] + stems["bass"] * 0.9 + stems["drums"] * 0.7)
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "128k", str(out)], check=True
        )
    print("wrote", out, out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
