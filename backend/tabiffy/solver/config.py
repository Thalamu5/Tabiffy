"""Solver cost weights, loaded from weights.json so they're easy to tune."""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path

_WEIGHTS_FILE = Path(__file__).with_name("weights.json")


@dataclass(frozen=True)
class SolverConfig:
    stretch4: float = 2.5
    stretch5: float = 7.0
    fingersImpossible: float = 1000.0  # noqa: N815 (matches the JSON keys)
    barre: float = 0.8
    skippedString: float = 1.5  # noqa: N815
    stringCrossing: float = 1.2  # noqa: N815
    highFret: float = 0.03  # noqa: N815
    highFretAbove12: float = 0.25  # noqa: N815
    openStringBonus: float = 0.6  # noqa: N815
    openStringBonusSingleNote: float = 0.2  # noqa: N815
    openFarFromNut: float = 0.12  # noqa: N815
    melodicCrossing: float = 0.8  # noqa: N815
    chordShapeBonus: float = 1.2  # noqa: N815
    move: float = 0.8
    moveSpeed: float = 1.0  # noqa: N815
    bigJump: float = 2.0  # noqa: N815
    bigJumpFrets: int = 4  # noqa: N815
    stayBonus: float = 0.3  # noqa: N815
    cutRingingNote: float = 1.5  # noqa: N815
    positionBehindIndex: float = 0.15  # noqa: N815
    maxVoicingsPerSlice: int = 24  # noqa: N815
    maxFingersSpanFrets: int = 5  # noqa: N815


def load_config(path: Path | None = None) -> SolverConfig:
    data = json.loads((path or _WEIGHTS_FILE).read_text())
    known = {f.name for f in fields(SolverConfig)}
    return SolverConfig(**{k: v for k, v in data.items() if k in known})
