"""The TabiffyScore document (SPEC section 4): camelCase in JSON, snake_case in Python.
Times are ticks at 960 per quarter note. See the field comments for the guitar conventions."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# A note name like "E2", "F#1" or "Bb3". Checked strictly because tunings end up in the score text alphaTab reads.
NoteName = Annotated[str, Field(pattern=r"^[A-G][#b]?-?[0-9]$")]

Instrument = Literal["guitar", "bass", "piano", "vocals", "other"]
TargetInstrument = Literal["guitar", "bass", "piano"]


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Meta(_Model):
    """Song details shown in the header."""

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
    """A chord name and how long it lasts."""

    tick: int
    duration_ticks: int
    symbol: str
    pcs: list[int] = Field(default_factory=list)
    confidence: float = 1.0


class Note(_Model):
    """One note: pitch and timing, plus string/fret/finger once the solver has placed it."""

    id: str
    tick: int
    duration_ticks: int
    midi: int
    velocity: int = 90
    # guitar / bass
    string: int | None = None  # 1 = highest-pitched string
    fret: int | None = None  # counted from the capo, as tab is normally written
    # piano
    hand: Literal["L", "R"] | None = None
    finger: int | Literal["T"] | None = None  # 0 open, 1-4 index..pinky, "T" thumb (piano: 1-5)
    # "slide", "hammer", "pull" (leading into `legato_to`) or "tap". A "suggestedTechnique" flag marks weak evidence.
    techniques: list[str] = Field(default_factory=list)
    legato_to: str | None = None  # id of the note a slide / hammer-on / pull-off leads into
    confidence: float = 1.0
    user_edited: bool = False
    # Solver/mapping notes for the UI, e.g. "outOfRange", "stretch", "barre".
    flags: list[str] = Field(default_factory=list)


class CapoSuggestion(_Model):
    capo: int
    shapes_key: str = ""
    cost: float = 0.0


class TuningSuggestion(_Model):
    """One suggested tuning with its score and the reason for it."""

    key: str  # preset key in tunings.TUNINGS
    label: str
    tuning: list[str]
    strings: int
    score: float  # lower = better fit
    relative: float = 0.0  # score minus the best score
    notes_below: int = 0
    reason: str = ""


class Track(_Model):
    """One instrument part: its notes plus how it is played (tuning, capo, transpose)."""

    id: str
    name: str
    source_instrument: Instrument = "other"
    target_instrument: TargetInstrument = "guitar"
    tuning: list[NoteName] = Field(default_factory=list, max_length=8)  # low -> high
    capo: int = Field(0, ge=0, le=24)
    transpose_semitones: int = 0
    program: int = 25  # General MIDI program used for playback
    notes: list[Note] = Field(default_factory=list)
    # Index of the track in the source file this one was built from.
    source_track_index: int | None = None
    capo_suggestion: CapoSuggestion | None = None
    tuning_suggestions: list[TuningSuggestion] = Field(default_factory=list)
    tuning_detected: bool = False  # the tuning was picked automatically from the notes


class SolverSettings(_Model):
    """User-facing knobs that affect stages 6-8 (mapping, solver, quantize)."""

    max_fret: int = 22
    open_string_preference: float = 1.0  # 0 = neutral, higher = more open strings
    simplify_chords: bool = False  # reduce voicings to at most 4 notes
    quantize: Literal["off", "1/8", "1/16", "1/16+triplets", "1/32"] = "1/16+triplets"
    tapping: bool = False  # the song uses two-hand tapping: allow notes played by the picking hand


class SyncPoint(_Model):
    """Where a tick of the score falls in the original recording."""

    tick: int
    seconds: float


class AudioInfo(_Model):
    """Present when the score was transcribed from an audio file."""

    duration_seconds: float = 0.0
    mode: str = "guitar"  # what the file contains: "guitar" | "bass" | "piano" | "vocals" | "other" | "mix"
    detected_bpm: float = 120.0
    tempo_factor: float = 1.0  # user override: 0.5 = half time, 2 = double time
    downbeat_shift: int = 0  # user override: move bar lines by N beats
    sync_points: list[SyncPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ScaleMatch(_Model):
    """One candidate key/scale, e.g. "F# Phrygian Dominant", with its spelled notes."""

    tonic: str
    tonic_pc: int
    name: str
    label: str
    family: str
    notes: list[str]
    pcs: list[int] = Field(default_factory=list)  # pitch class of each note above (C=0 ... B=11)
    fit: float  # share of played notes inside the scale (0-1)
    relative: float = 0.0  # how far behind the best match (0 = best)


class KeyAnalysis(_Model):
    """Why we think the song is in its key; shown when the key is clicked."""

    key: str
    scale: ScaleMatch
    alternatives: list[ScaleMatch] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    histogram: list[float] = Field(default_factory=list)  # share of playing time per note, C..B
    reasons: list[str] = Field(default_factory=list)


class TabiffyScore(_Model):
    """The whole song: meta, tempo, chords, tracks, settings and audio info."""

    version: int = 1
    meta: Meta = Field(default_factory=Meta)
    tempo_map: list[TempoPoint] = Field(default_factory=lambda: [TempoPoint(tick=0, bpm=120)])
    ticks_per_quarter: int = 960
    chords: list[ChordLabel] = Field(default_factory=list)
    tracks: list[Track] = Field(default_factory=list)
    settings: SolverSettings = Field(default_factory=SolverSettings)
    audio: AudioInfo | None = None
    key_analysis: KeyAnalysis | None = None

    def to_json(self) -> str:
        return self.model_dump_json(by_alias=True, exclude_none=True, indent=2)
