"""Audio -> notes: decode (ffmpeg), transcribe (Basic Pitch), find beats (librosa), then the same
solver as MIDI. Each upload is one part; separating instruments is up to the user beforehand.
Heavy libraries are imported lazily so the MIDI path works without them."""

import os as _os
import tempfile as _tempfile

# librosa's helper (numba) saves compiled code next to its own files, or else in the user's home folder.
# When the app runs as a restricted user neither is writable and every audio job crashes, so give it a
# private, writable cache folder unless one is already configured.
_os.environ.setdefault("NUMBA_CACHE_DIR", _os.path.join(_tempfile.gettempdir(), "tabiffy-numba-cache"))
