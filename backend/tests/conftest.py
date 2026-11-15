from pathlib import Path

import pytest

from tabiffy.models import Note

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


def make_notes(spec: list[tuple[int, int, int]]) -> list[Note]:
    """spec: (tick, duration, midi)"""
    return [Note(id=f"n{i}", tick=t, duration_ticks=d, midi=m) for i, (t, d, m) in enumerate(spec)]
