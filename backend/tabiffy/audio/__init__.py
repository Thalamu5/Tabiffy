"""Audio -> notes (milestones M2 + M3).

Stages: decode (ffmpeg) -> note transcription (Basic Pitch) -> beats/tempo/meter (librosa)
-> beat-aligned ticks -> the same solver as MIDI. Each upload is transcribed as one part;
instrument separation, if wanted, is done by the user before uploading.

Heavy libraries (basic-pitch, librosa) are imported lazily so the MIDI path keeps working
when they aren't installed.
"""
