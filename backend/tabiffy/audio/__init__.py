"""Audio -> notes: decode (ffmpeg), transcribe (Basic Pitch), find beats (librosa), then the same
solver as MIDI. Each upload is one part; separating instruments is up to the user beforehand.
Heavy libraries are imported lazily so the MIDI path works without them."""
