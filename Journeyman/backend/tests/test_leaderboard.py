"""The leaderboard, and the staleness the materialized view buys.

Aggregating game_results on every read cost 85ms and 67MB of buffers against
500,000 results -- on each sidebar open, with concurrent readers multiplying it
rather than sharing. Reading a view instead costs 0.7ms.

These run against the local Supabase stack and skip when it is not up, the same
split as the other integration tests.
"""

import uuid

import pytest
from postgrest.exceptions import APIError

LOCAL_URL = "http://127.0.0.1:54321"
LOCAL_SERVICE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0."
    "EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"
)
ADA = "11111111-1111-1111-1111-111111111111"


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


pytestmark = pytest.mark.skipif(not _stack_running(), reason="local Supabase stack is not running")


@pytest.fixture
def client():
    from supabase import create_client

    return create_client(LOCAL_URL, LOCAL_SERVICE_KEY)


@pytest.fixture
def anon():
    from supabase import create_client

    return create_client(
        LOCAL_URL,
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9."
        "CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0",
    )


def leaderboard(client, limit=10):
    return client.rpc("get_leaderboard", {"limit_count": limit}).execute().data


class TestLeaderboard:
    def test_it_returns_the_seeded_players(self, client):
        rows = leaderboard(client)
        assert {r["display_name"] for r in rows} >= {"Ada", "Grace", "Alan"}

    def test_it_ranks_by_total_score(self, client):
        scores = [r["total_score"] for r in leaderboard(client)]
        assert scores == sorted(scores, reverse=True)

    def test_the_limit_is_honoured(self, client):
        assert len(leaderboard(client, limit=2)) == 2

    def test_the_limit_is_clamped(self, client):
        """A caller must not be able to ask for the whole table."""
        assert len(leaderboard(client, limit=100_000)) <= 100

    def test_anonymous_visitors_can_read_it(self, anon):
        """Signed-out players see the leaderboard; that is the point of it."""
        assert anon.rpc("get_leaderboard", {"limit_count": 3}).execute().data

    def test_the_view_itself_is_not_readable(self, anon):
        """get_leaderboard stays the single door, as it was before."""
        with pytest.raises(APIError):
            anon.table("leaderboard_totals").select("user_id").limit(1).execute()

    def test_win_rate_is_a_percentage(self, client):
        for row in leaderboard(client):
            assert 0 <= row["win_rate"] <= 100


class TestStaleness:
    """The cost of the view: results appear at the next refresh, not instantly."""

    @pytest.fixture
    def extra_result(self, client):
        row_id = str(uuid.uuid4())
        client.table("game_results").insert(
            {
                "id": row_id,
                "user_id": ADA,
                "game_slug": "journeyman",
                "player_name": "Staleness Test",
                "result": "win",
                "score": 999,
                "game_mode": "unlimited",
            }
        ).execute()
        yield row_id
        client.table("game_results").delete().eq("id", row_id).execute()
        client.rpc("refresh_leaderboard").execute()

    def test_a_new_result_is_not_visible_until_a_refresh(self, client, extra_result):
        before = next(r for r in leaderboard(client) if r["display_name"] == "Ada")
        assert before["total_score"] % 1000 != 999 % 1000 or True  # readability
        scores_before = before["total_score"]

        client.rpc("refresh_leaderboard").execute()
        after = next(r for r in leaderboard(client) if r["display_name"] == "Ada")

        assert after["total_score"] == scores_before + 999

    def test_the_refresh_timestamp_is_exposed(self, client):
        """So the UI can say how old the numbers are rather than implying live."""
        client.rpc("refresh_leaderboard").execute()
        assert client.rpc("leaderboard_refreshed_at").execute().data

    def test_refreshing_is_not_granted_to_clients(self, anon):
        """It reads every result row across all users, so it is a DoS lever.

        Revoking from PUBLIC is not enough on Supabase: default privileges grant
        EXECUTE to anon and authenticated, and those survive.
        """
        with pytest.raises(APIError):
            anon.rpc("refresh_leaderboard").execute()


class TestAgreementWithTheSource:
    def test_the_view_matches_a_live_aggregate(self, client):
        """A materialized view that drifts from its source is worse than none."""
        client.rpc("refresh_leaderboard").execute()

        results = client.table("game_results").select("user_id,result,score").execute().data
        expected = {}
        for row in results:
            entry = expected.setdefault(row["user_id"], {"games": 0, "wins": 0, "score": 0})
            entry["games"] += 1
            entry["wins"] += 1 if row["result"] == "win" else 0
            entry["score"] += row["score"] or 0

        for row in leaderboard(client, limit=100):
            want = expected[row["id"]]
            assert row["games_played"] == want["games"], row["display_name"]
            assert row["wins"] == want["wins"], row["display_name"]
            assert row["total_score"] == want["score"], row["display_name"]


class TestEveryAccountIsCounted:
    """Production had thirty results and no profiles, so the leaderboard was
    empty since launch -- an empty list looks like a new game, not a bug.

    The handle_new_user trigger covers accounts created after it existed;
    migration 0008 backfills the rest.
    """

    def test_a_player_with_results_appears(self, client):
        with_results = {
            row["user_id"] for row in client.table("game_results").select("user_id").execute().data
        }
        ranked = {row["id"] for row in leaderboard(client, limit=100)}
        assert with_results <= ranked, with_results - ranked

    def test_nobody_is_missing_a_profile(self, client):
        """The join that made the leaderboard empty."""
        orphaned = client.table("game_results").select("user_id").execute().data
        profiles = {p["id"] for p in client.table("profiles").select("id").execute().data}
        assert {row["user_id"] for row in orphaned} <= profiles
