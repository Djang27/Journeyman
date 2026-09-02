"""Tests for the Supabase-backed session store.

Two layers, deliberately separated:

* Row mapping is pure, so it is tested directly with no network at all. This is
  where the bugs actually live -- a dropped field or a mangled timestamp.
* The store itself runs against the LOCAL Supabase stack (`supabase start`),
  and skips when that is not running. Local Docker is not a third-party API, so
  this does not break the rule that CI must never depend on one; CI simply skips
  these and runs the mapping tests.
"""

from datetime import UTC, datetime, timedelta

import pytest
from config import Config, ConfigError
from sessions import Session, SessionError
from supabase_store import SupabaseSessionStore, from_row, to_row

T0 = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)

# Seeded by supabase/seed.sql. game_sessions.user_id is a foreign key to
# auth.users, so a session can only ever be created for a real account -- these
# tests need ids that actually exist.
ADA = "11111111-1111-1111-1111-111111111111"
GRACE = "22222222-2222-2222-2222-222222222222"
ALAN = "33333333-3333-3333-3333-333333333333"


def make_session(**overrides):
    params = {
        "id": "11111111-2222-3333-4444-555555555555",
        "game_slug": "journeyman",
        "mode": "unlimited",
        "answer": ["boston celtics", "miami heat", "utah jazz"],
        "player_name": "Test Journeyman",
        "player_id": 1,
        "results": [None, None, None],
        "guesses": [None, None, None],
        "started_at": T0,
    }
    params.update(overrides)
    return Session(**params)


class TestRowMapping:
    """Pure, no database. A round trip must preserve everything the game needs."""

    def test_round_trip_preserves_a_fresh_session(self):
        session = make_session()
        assert from_row(to_row(session)) == session

    def test_round_trip_preserves_a_finished_session(self):
        session = make_session(
            results=["green", "green", "green"],
            guesses=["celtics", "heat", "jazz"],
            wrong_guesses=1,
            hint_used=True,
            hard_mode=True,
            status="won",
            finished_at=T0 + timedelta(seconds=90),
            score=1234,
        )
        assert from_row(to_row(session)) == session

    def test_round_trip_preserves_a_daily_with_a_user(self):
        session = make_session(
            mode="daily",
            user_id=ADA,
            puzzle_date="2026-08-29",
        )
        assert from_row(to_row(session)) == session

    def test_the_answer_is_stored_under_the_answer_column(self):
        """It must land in `answer`, the column no client policy can read."""
        row = to_row(make_session())
        assert row["answer"]["teams"] == ["boston celtics", "miami heat", "utah jazz"]
        assert "teams" not in row["state"]

    def test_timestamps_survive_postgrest_string_form(self):
        row = to_row(make_session(finished_at=T0 + timedelta(seconds=45)))
        # PostgREST hands back ISO strings, sometimes with a trailing Z.
        row["started_at"] = "2026-08-29T12:00:00Z"
        row["finished_at"] = "2026-08-29T12:00:45Z"

        session = from_row(row)
        assert session.started_at == T0
        assert (session.finished_at - session.started_at).total_seconds() == 45

    def test_a_null_finished_at_stays_none(self):
        assert from_row(to_row(make_session())).finished_at is None

    def test_missing_jsonb_blobs_do_not_crash(self):
        """Defensive: a hand-inserted row may have nulls the app never writes."""
        row = to_row(make_session())
        row["answer"] = None
        row["state"] = None
        session = from_row(row)
        assert session.answer == []
        assert session.wrong_guesses == 0


class TestConfig:
    def test_reports_no_database_when_unset(self):
        assert Config(environ={}).use_database is False

    def test_reports_a_database_when_both_values_are_present(self):
        config = Config(environ={"SUPABASE_URL": "http://x", "SUPABASE_SERVICE_ROLE_KEY": "k"})
        assert config.use_database is True

    def test_require_database_names_what_is_missing(self):
        with pytest.raises(ConfigError, match="SUPABASE_SERVICE_ROLE_KEY"):
            Config(environ={"SUPABASE_URL": "http://x"}).require_database()

    def test_require_database_names_both_when_both_are_missing(self):
        with pytest.raises(ConfigError, match="SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY"):
            Config(environ={}).require_database()


# --------------------------------------------------------------------------
# Integration: real PostgREST, real Postgres, local only.
# --------------------------------------------------------------------------

LOCAL_URL = "http://127.0.0.1:54321"
LOCAL_SERVICE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0."
    "EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"
)


def _local_stack_running():
    import urllib.error
    import urllib.request

    try:
        urllib.request.urlopen(f"{LOCAL_URL}/rest/v1/", timeout=1)
        return True
    except urllib.error.HTTPError:
        return True  # answered, just not anonymously
    except Exception:
        return False


integration = pytest.mark.skipif(
    not _local_stack_running(),
    reason="local Supabase stack is not running (`supabase start`)",
)


PUZZLE_DATES = ("2026-06-11", "2026-06-12")


@pytest.fixture
def store():
    from supabase import create_client

    client = create_client(LOCAL_URL, LOCAL_SERVICE_KEY)

    # A daily session carries a composite foreign key to `puzzles`, so the
    # scheduled puzzle has to exist first. That constraint is the point -- a
    # daily can never reference a date nobody scheduled -- so the fixture
    # satisfies it rather than the test working around it.
    for puzzle_date in PUZZLE_DATES:
        client.table("puzzles").upsert(
            {
                "game_slug": "journeyman",
                "puzzle_date": puzzle_date,
                "payload": {"player_name": "Test Journeyman", "teams": ["boston celtics"]},
            }
        ).execute()

    created = []
    store = SupabaseSessionStore(client)
    original_create = store.create

    def tracking_create(session):
        result = original_create(session)
        created.append(result.id)
        return result

    store.create = tracking_create
    yield store

    for session_id in created:
        client.table("game_sessions").delete().eq("id", session_id).execute()
    for puzzle_date in PUZZLE_DATES:
        client.table("puzzles").delete().eq("game_slug", "journeyman").eq(
            "puzzle_date", puzzle_date
        ).execute()


@integration
class TestAgainstLocalSupabase:
    def test_create_then_get_round_trips_through_postgres(self, store):
        session = store.create(make_session())
        loaded = store.get(session.id)

        assert loaded is not None
        assert loaded.answer == session.answer
        assert loaded.status == "active"

    def test_get_returns_none_for_an_unknown_id(self, store):
        assert store.get("00000000-0000-0000-0000-000000000000") is None

    def test_update_persists_progress(self, store):
        from dataclasses import replace

        session = store.create(make_session())
        store.update(replace(session, results=["green", None, None], wrong_guesses=1))

        reloaded = store.get(session.id)
        assert reloaded.results == ["green", None, None]
        assert reloaded.wrong_guesses == 1

    def test_the_database_refuses_a_second_daily(self, store):
        """The real guarantee: a partial unique index, not application code."""
        user_id = ADA
        store.create(make_session(mode="daily", user_id=user_id, puzzle_date="2026-06-11"))

        with pytest.raises(SessionError, match="daily already played"):
            store.create(
                make_session(
                    id="99999999-8888-7777-6666-555555555555",
                    mode="daily",
                    user_id=user_id,
                    puzzle_date="2026-06-11",
                )
            )

    def test_a_daily_cannot_reference_an_unscheduled_date(self, store):
        """The composite foreign key from migration 0002.

        A daily session must point at a real scheduled puzzle, so a bug in
        puzzle selection surfaces as a refused insert rather than a game nobody
        can ever be scored against.
        """
        with pytest.raises(Exception, match="game_sessions_puzzle_fkey"):
            store.create(make_session(mode="daily", user_id=ADA, puzzle_date="2099-01-01"))

    def test_a_session_cannot_reference_an_unknown_user(self, store):
        """The other foreign key, which fires first and is easy to miss."""
        with pytest.raises(Exception, match="game_sessions_user_id_fkey"):
            store.create(make_session(user_id="55555555-5555-5555-5555-555555555555"))

    def test_find_daily_locates_an_existing_attempt(self, store):
        user_id = GRACE
        created = store.create(
            make_session(mode="daily", user_id=user_id, puzzle_date="2026-06-11")
        )

        found = store.find_daily(user_id, "2026-06-11")
        assert found is not None and found.id == created.id

    def test_find_daily_is_scoped_to_the_date(self, store):
        user_id = ALAN
        store.create(make_session(mode="daily", user_id=user_id, puzzle_date="2026-06-11"))
        assert store.find_daily(user_id, "2026-06-12") is None

    def test_unlimited_sessions_are_not_blocked(self, store):
        user_id = ADA
        first = store.create(make_session(mode="unlimited", user_id=user_id))
        second = store.create(
            make_session(
                id="44444444-4444-4444-4444-444444444444", mode="unlimited", user_id=user_id
            )
        )
        assert first.id != second.id
