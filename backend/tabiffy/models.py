"""The canonical `TabiffyScore` JSON document (SPEC section 4).

All JSON keys are camelCase; Python attributes are snake_case. Serialize with
`model_dump(by_alias=True)` / `model_dump_json(by_alias=True)`.

Conventions:
- `tick` / `durationTicks` use `ticksPerQuarter` (960) resolution.
- Guitar/bass: `string` 1 = highest-pitched string. `fret` is counted from the
  capo (fret 0 with capo 2 sounds the open string + 2 semitones), which is how
  tab is normally written and how alphaTab/Guitar Pro interpret it.
- `finger`: 0 = open string, 1-4 = index..pinky, "T" = thumb. Piano: 1-5, thumb = 1.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

Instrument = Literal["guitar", "bass", "piano", "vocals", "other"]
TargetInstrument = Literal["guitar", "bass", "piano"]


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Meta(_Model):
    title: str = ""
    artist: str = ""
    source_file: str = ""
    bpm: float = 120.0
    time_signature: tuple[int, int] = (4, 4)
    key: str = ""


class TempoPoint(_Model):
    tick: int
    bpm: float


class ChordLabel(_Model):
    tick: int
    duration_ticks: int
    symbol: str
    pcs: list[int] = Field(default_factory=list)
    confidence: float = 1.0


class Note(_Model):
    id: str
    tick: int
    duration_ticks: int
    midi: int
    velocity: int = 90
    # guitar / bass
    string: int | None = None
    fret: int | None = None
    # piano
    hand: Literal["L", "R"] | None = None
    finger: int | Literal["T"] | None = None
    techniques: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    user_edited: bool = False
    # Solver/mapping notes for the UI, e.g. "outOfRange", "stretch", "barre".
    flags: list[str] = Field(default_factory=list)


class CapoSuggestion(_Model):
    capo: int
    shapes_key: str = ""
    cost: float = 0.0


class Track(_Model):
    id: str
    name: str
    source_instrument: Instrument = "other"
    target_instrument: TargetInstrument = "guitar"
    tuning: list[str] = Field(default_factory=list)  # low -> high
    capo: int = 0
    transpose_semitones: int = 0
    program: int = 25  # General MIDI program used for playback
    notes: list[Note] = Field(default_factory=list)
    # Index of the track in the source file this one was built from.
    source_track_index: int | None = None
    capo_suggestion: CapoSuggestion | None = None


class SolverSettings(_Model):
    """User-facing knobs that affect stages 6-8 (mapping, solver, quantize)."""

    max_fret: int = 22
    open_string_preference: float = 1.0  # 0 = neutral, higher = more open strings
    simplify_chords: bool = False  # reduce voicings to at most 4 notes
    quantize: Literal["off", "1/8", "1/16", "1/16+triplets", "1/32"] = "1/16"


class SyncPoint(_Model):
    """Where a tick of the score falls in the original recording."""

    tick: int
    seconds: float


class AudioInfo(_Model):
    """Present when the score was transcribed from an audio file."""

    duration_seconds: float = 0.0
    separated: bool = False  # stems were split with Demucs
    mode: str = "full"  # "full" or a solo instrument: "guitar" | "bass" | "piano" | "other"
    detected_bpm: float = 120.0
    tempo_factor: float = 1.0  # user override: 0.5 = half time, 2 = double time
    downbeat_shift: int = 0  # user override: move bar lines by N beats
    sync_points: list[SyncPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TabiffyScore(_Model):
    version: int = 1
    meta: Meta = Field(default_factory=Meta)
    tempo_map: list[TempoPoint] = Field(default_factory=lambda: [TempoPoint(tick=0, bpm=120)])
    ticks_per_quarter: int = 960
    chords: list[ChordLabel] = Field(default_factory=list)
    tracks: list[Track] = Field(default_factory=list)
    settings: SolverSettings = Field(default_factory=SolverSettings)
    audio: AudioInfo | None = None

    def to_json(self) -> str:
        return self.model_dump_json(by_alias=True, exclude_none=True, indent=2)
