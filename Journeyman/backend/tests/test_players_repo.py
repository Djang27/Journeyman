"""Mapping players into the database, and the curation gate.

The row mapping is pure and tested directly. The repo runs against the local
Supabase stack and skips when it is not up, the same split as the session store.
"""

import json
from pathlib import Path

import pytest
from players_repo import PlayersRepo, stints_from_teams, teams_of, to_row

POOL = Path(__file__).parents[1] / "nba_players.json"
GOOD = ["boston celtics", "miami heat", "utah jazz"]


def player(**overrides):
    base = {"id": 1, "name": "Test Journeyman", "teams": GOOD, "ppg": 12.5}
    base.update(overrides)
    return base


class TestRowMapping:
    def test_teams_become_stints(self):
        row = to_row(player(), "test")
        assert [s["team"] for s in row["stints"]] == GOOD

    def test_legacy_players_import_with_no_seasons(self):
        """nba_players.json has no years, so era validation cannot apply yet."""
        row = to_row(player(), "test")
        assert all(s["from_season"] is None for s in row["stints"])
        assert row["first_season"] is None

    def test_seasons_are_carried_when_a_source_provides_them(self):
        stints = [
            {"team": "seattle supersonics", "from_season": 1995, "to_season": 1998},
            {"team": "miami heat", "from_season": 1998, "to_season": 2001},
        ]
        row = to_row({"id": 2, "name": "X", "stints": stints}, "test")
        assert (row["first_season"], row["last_season"]) == (1995, 1998)

    def test_a_return_stays_a_separate_stint(self):
        teams = ["cleveland cavaliers", "miami heat", "cleveland cavaliers"]
        assert len(to_row(player(teams=teams), "test")["stints"]) == 3

    def test_validation_runs_at_import_time(self):
        assert to_row(player(), "test")["validation_status"] == "ok"

    def test_a_flagged_career_records_why(self):
        teams = ["detroit pistons", "milwaukee bucks", "detroit pistons", "milwaukee bucks"]
        row = to_row(player(teams=teams), "test")
        assert row["validation_status"] == "review"
        assert "alternation" in row["validation_notes"]

    def test_an_impossible_career_is_marked_reject(self):
        row = to_row(player(teams=["brooklyn nets", "new jersey nets"]), "test")
        assert row["validation_status"] == "reject"

    def test_an_import_never_promotes_a_player(self):
        """The curation gate. An ingestion bug must not become a puzzle."""
        assert "is_active_for_puzzles" not in to_row(player(), "test")

    def test_the_source_is_recorded(self):
        assert to_row(player(), "kaggle-2026")["source"] == "kaggle-2026"

    def test_teams_of_inverts_the_mapping(self):
        assert teams_of({"stints": stints_from_teams(GOOD)}) == GOOD

    def test_the_whole_shipped_pool_maps_without_error(self):
        with open(POOL, encoding="utf-8") as f:
            rows = [to_row(p, "nba_players.json") for p in json.load(f)["players"]]
        assert len(rows) == 200
        assert all(r["stints"] for r in rows)
        assert {r["validation_status"] for r in rows} <= {"ok", "review", "reject"}


LOCAL_URL = "http://127.0.0.1:54321"
LOCAL_SERVICE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0."
    "EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"
)


def _stack_running():
    import urllib.error
    import urllib.request

    try:
        urllib.request.urlopen(f"{LOCAL_URL}/rest/v1/", timeout=1)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


@pytest.fixture
def repo():
    from supabase import create_client

    client = create_client(LOCAL_URL, LOCAL_SERVICE_KEY)
    ids = [900001, 900002, 900003]
    yield PlayersRepo(client)
    for player_id in ids:
        client.table("players").delete().eq("id", player_id).execute()


@pytest.mark.skipif(not _stack_running(), reason="local Supabase stack is not running")
class TestAgainstLocalSupabase:
    def test_upsert_then_read_back(self, repo):
        repo.upsert_many([player(id=900001)], source="test")
        stored = repo.get(900001)
        assert stored["name"] == "Test Journeyman"
        assert teams_of(stored) == GOOD

    def test_imported_players_are_not_puzzle_eligible(self, repo):
        repo.upsert_many([player(id=900001)], source="test")
        assert repo.get(900001)["is_active_for_puzzles"] is False

    def test_promotion_is_a_separate_act(self, repo):
        repo.upsert_many([player(id=900001)], source="test")
        repo.set_active(900001, True)
        assert repo.get(900001)["is_active_for_puzzles"] is True

    def test_reimporting_does_not_demote_a_promoted_player(self, repo):
        """A refresh must not quietly empty the puzzle rotation."""
        repo.upsert_many([player(id=900001)], source="test")
        repo.set_active(900001, True)
        repo.upsert_many([player(id=900001, name="Renamed")], source="test")

        stored = repo.get(900001)
        assert stored["name"] == "Renamed"
        assert stored["is_active_for_puzzles"] is True

    def test_the_review_queue_is_a_query(self, repo):
        bad = player(id=900002, teams=["brooklyn nets", "new jersey nets"])
        repo.upsert_many([player(id=900001), bad], source="test")

        flagged = {p["id"] for p in repo.needing_review()}
        assert 900002 in flagged
        assert 900001 not in flagged

    def test_the_active_pool_holds_only_promoted_players(self, repo):
        repo.upsert_many([player(id=900001), player(id=900003)], source="test")
        repo.set_active(900001, True)

        pool = {p["id"] for p in repo.active_pool()}
        assert 900001 in pool
        assert 900003 not in pool
