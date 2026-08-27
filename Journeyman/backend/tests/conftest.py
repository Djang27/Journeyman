import json
from datetime import date
from pathlib import Path

import pytest

FIXTURE_DB = Path(__file__).parent / "fixtures" / "players_sample.json"


@pytest.fixture
def sample_players():
    with FIXTURE_DB.open(encoding="utf-8") as f:
        return json.load(f)["players"]


@pytest.fixture
def player_db(monkeypatch):
    """Point generate_players at the fixture database instead of the real one.

    Every test that touches player selection uses this, so the suite never
    depends on the contents of nba_players.json -- which changes whenever the
    ingestion job runs.
    """
    import generate_players

    monkeypatch.setattr(generate_players, "PLAYER_DATABASE_PATH", FIXTURE_DB)
    return generate_players


@pytest.fixture
def frozen_date(monkeypatch):
    """Pin the Eastern-time 'today' so daily-puzzle tests are deterministic."""

    def _freeze(module, year, month, day):
        monkeypatch.setattr(module, "_eastern_today", lambda: date(year, month, day))

    return _freeze
