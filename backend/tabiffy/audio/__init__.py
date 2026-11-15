"""Audio -> notes (milestones M2 + M3).

Stages: decode (ffmpeg) -> stem separation (Demucs) -> note transcription (Basic Pitch)
-> beats/tempo/meter (librosa) -> beat-aligned ticks -> the same solver as MIDI.

Heavy libraries (torch, demucs, basic-pitch, librosa) are imported lazily so the MIDI
path keeps working when they aren't installed.
"""
