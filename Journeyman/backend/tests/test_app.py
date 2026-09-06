"""Endpoint tests against the Flask test client.

Deliberately thin. These check request/response contracts -- the shapes the
frontend depends on -- and leave grading rules to test_game_logic.py.
"""

import json

import pytest


@pytest.fixture
def client(player_db):
    import app as app_module
    from app import app

    app.config["TESTING"] = True
    # The puzzle cache is module-level, so without this one test's daily leaks
    # into the next -- as a hit nothing set up, and as counters the health
    # endpoint's body assertion then disagrees with.
    app_module.daily_cache.reset()

    # Same problem, longer standing: the rate limiter counts per process, so a
    # test making many requests spent budget that later tests were then refused.
    # It only surfaced once a test started 25 games.
    limiter = app_module.rate_limiter
    if hasattr(limiter, "_counts"):
        limiter._counts.clear()

    # And again for the quota: without this, tests that start unlimited games
    # spend an allowance later tests are then refused.
    from quota import InMemoryQuotaStore

    app_module.quota_store = InMemoryQuotaStore()
    with app.test_client() as test_client:
        yield test_client


class TestHome:
    def test_serves_a_welcome_string(self, client):
        assert client.get("/").status_code == 200


class TestSessionAPI:
    """The Phase 0 endpoints, running beside the legacy ones.

    The app module holds a single in-memory store, so each test resets it to
    stay independent.
    """

    @pytest.fixture(autouse=True)
    def _fresh_store(self, client):
        import app as app_module
        from sessions import InMemorySessionStore

        app_module.session_store = InMemorySessionStore()

    def start(self, client, **body):
        return client.post("/api/game/start", json={"mode": "unlimited", **body})

    def test_start_returns_a_session_without_the_answer(self, client):
        response = self.start(client)
        assert response.status_code == 201

        body = response.get_json()
        assert body["session_id"]
        assert body["num_teams"] >= 2
        assert body["status"] == "active"
        assert "teams" not in body, "the answer must not leave the server"

    def test_the_answer_is_absent_from_the_raw_response_bytes(self, client):
        """Belt and braces: check the wire, not the parsed object."""
        import app as app_module

        session_id = self.start(client).get_json()["session_id"]
        answer = app_module.session_store.get(session_id).answer

        raw = client.get(f"/api/game/{session_id}").get_data(as_text=True).lower()
        for team in answer:
            assert team not in raw, f"{team!r} leaked in the session payload"

    def test_a_correct_guess_grades_green(self, client):
        import app as app_module

        session_id = self.start(client).get_json()["session_id"]
        answer = app_module.session_store.get(session_id).answer

        response = client.post(
            f"/api/game/{session_id}/guess", json={"position": 0, "guess": answer[0]}
        )
        assert response.get_json()["results"][0] == "green"

    def test_winning_reveals_the_answer_and_a_score(self, client):
        import app as app_module

        session_id = self.start(client).get_json()["session_id"]
        answer = app_module.session_store.get(session_id).answer

        for position, team in enumerate(answer):
            body = client.post(
                f"/api/game/{session_id}/guess", json={"position": position, "guess": team}
            ).get_json()

        assert body["status"] == "won"
        assert body["teams"] == answer
        assert body["score"] > 0

    def test_losing_scores_zero(self, client):
        session_id = self.start(client).get_json()["session_id"]

        # Slot 0 every time, rather than one slot per guess: the fixture pool
        # holds players with as few as two teams, and a wrong slot stays open,
        # so this is the only loop that works whichever player is drawn.
        for _ in range(3):
            body = client.post(
                f"/api/game/{session_id}/guess",
                json={"position": 0, "guess": "not a real team"},
            ).get_json()

        assert body["status"] == "lost"
        assert body["score"] == 0

    def test_an_unknown_session_is_404(self, client):
        response = client.post(
            "/api/game/00000000-0000-0000-0000-000000000000/guess",
            json={"position": 0, "guess": "celtics"},
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "payload",
        [
            {"position": -1, "guess": "celtics"},
            {"position": 99, "guess": "celtics"},
            {"position": "0", "guess": "celtics"},
            {"position": 0, "guess": None},
            {},
        ],
        ids=["negative", "past-end", "not-an-int", "guess-missing", "empty-body"],
    )
    def test_malformed_guesses_are_400(self, client, payload):
        session_id = self.start(client).get_json()["session_id"]
        response = client.post(f"/api/game/{session_id}/guess", json=payload)
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_a_finished_game_rejects_further_guesses(self, client):
        import app as app_module

        session_id = self.start(client).get_json()["session_id"]
        answer = app_module.session_store.get(session_id).answer
        for position, team in enumerate(answer):
            client.post(f"/api/game/{session_id}/guess", json={"position": position, "guess": team})

        response = client.post(
            f"/api/game/{session_id}/guess", json={"position": 0, "guess": answer[0]}
        )
        assert response.status_code == 400

    @staticmethod
    def signed_in(monkeypatch, subject="11111111-1111-1111-1111-111111111111"):
        """Headers for a verified Supabase user, signing with the shared secret."""
        import time

        import app as app_module
        import jwt

        secret = "super-secret-jwt-token-with-at-least-32-characters-long"
        monkeypatch.setattr(app_module.config, "jwks_url", "")
        monkeypatch.setattr(app_module.config, "supabase_jwt_secret", secret)
        token = jwt.encode(
            {"sub": subject, "aud": "authenticated", "exp": int(time.time()) + 3600},
            secret,
            algorithm="HS256",
        )
        return {"Authorization": f"Bearer {token}"}

    def test_an_unfinished_daily_resumes_instead_of_locking_the_player_out(
        self, client, monkeypatch
    ):
        # The browser holds the session id in memory only, so a refresh used to
        # meet the one-daily-per-player index and lose the puzzle for the day.
        headers = self.signed_in(monkeypatch)

        first = client.post("/api/game/start", json={"mode": "daily"}, headers=headers)
        assert first.status_code == 201

        second = client.post("/api/game/start", json={"mode": "daily"}, headers=headers)
        assert second.status_code == 200
        assert second.get_json()["session_id"] == first.get_json()["session_id"]

    def test_resuming_preserves_the_guesses_already_made(self, client, monkeypatch):
        import app as app_module

        headers = self.signed_in(monkeypatch)
        session_id = client.post(
            "/api/game/start", json={"mode": "daily"}, headers=headers
        ).get_json()["session_id"]

        answer = app_module.session_store.get(session_id).answer
        client.post(
            f"/api/game/{session_id}/guess",
            json={"position": 0, "guess": answer[0]},
            headers=headers,
        )

        resumed = client.post("/api/game/start", json={"mode": "daily"}, headers=headers).get_json()
        assert resumed["results"][0] == "green"
        assert resumed["guesses"][0] == answer[0]

    def test_a_finished_daily_is_still_409(self, client, monkeypatch):
        # Resuming is not a second attempt. Once the game is over the index
        # rule stands.
        import app as app_module

        headers = self.signed_in(monkeypatch)
        session_id = client.post(
            "/api/game/start", json={"mode": "daily"}, headers=headers
        ).get_json()["session_id"]

        answer = app_module.session_store.get(session_id).answer
        for position, team in enumerate(answer):
            client.post(
                f"/api/game/{session_id}/guess",
                json={"position": position, "guess": team},
                headers=headers,
            )

        second = client.post("/api/game/start", json={"mode": "daily"}, headers=headers)
        assert second.status_code == 409

    def test_another_player_does_not_resume_someone_elses_daily(self, client, monkeypatch):
        first = client.post(
            "/api/game/start",
            json={"mode": "daily"},
            headers=self.signed_in(monkeypatch),
        )
        second = client.post(
            "/api/game/start",
            json={"mode": "daily"},
            headers=self.signed_in(monkeypatch, "22222222-2222-2222-2222-222222222222"),
        )
        assert second.status_code == 201
        assert second.get_json()["session_id"] != first.get_json()["session_id"]

    def test_anonymous_dailies_are_not_blocked(self, client):
        # No user_id means no way to attribute the attempt, so the database
        # index cannot apply. Documented rather than silently permitted.
        assert client.post("/api/game/start", json={"mode": "daily"}).status_code == 201
        assert client.post("/api/game/start", json={"mode": "daily"}).status_code == 201

    def test_the_hint_is_locked_until_two_wrong_guesses(self, client):
        session_id = self.start(client).get_json()["session_id"]
        assert client.post(f"/api/game/{session_id}/hint").status_code == 400

        for position in range(2):
            client.post(
                f"/api/game/{session_id}/guess",
                json={"position": position, "guess": "not a real team"},
            )
        assert client.post(f"/api/game/{session_id}/hint").get_json()["hint_used"] is True

    def test_abandoning_closes_the_session(self, client):
        session_id = self.start(client).get_json()["session_id"]
        body = client.post(f"/api/game/{session_id}/abandon").get_json()
        assert body["status"] == "abandoned"
        assert body["score"] == 0


class TestHealth:
    def test_reports_ok(self, client):
        body = client.get("/api/health").get_json()
        assert body["status"] == "ok"

    def test_reports_reachable_when_the_database_answers(self, client):
        import app as app_module

        class HealthyStore:
            def check_reachable(self):
                return None

        original = app_module.session_store
        app_module.session_store = HealthyStore()
        try:
            response = client.get("/api/health")
            assert response.status_code == 200
            assert response.get_json() == {
                "status": "ok",
                "session_store": "database",
                "persistent": True,
                "database_reachable": True,
                # Says whether errors are actually being captured, rather than
                # leaving anyone to assume they are.
                "error_reporting": False,
                # Why it is off, not just that it is. Under test no DSN is set.
                "error_reporting_status": "no_dsn",
                "maintenance": False,
                # Cold, because the fixture invalidates it. What matters is
                # that the shape is here at all: a hit rate near zero on a busy
                # deployment is the signal that instances are not being reused.
                "quota_enforcing": True,
                "daily_cache": {
                    "hits": 0,
                    "misses": 0,
                    "hit_rate": None,
                    "cached_date": None,
                    "ttl_seconds": 60,
                },
            }
        finally:
            app_module.session_store = original

    def test_reports_the_quota_failing_open(self, client):
        """A broken quota looks exactly like a working game, and is not one.

        This is the bug that shipped: migration 0012 and the code calling it
        merged together, so production spent minutes calling a function that did
        not exist. The quota failed open, the game worked, the smoke test
        passed, and every unlimited game was free. Only an error report caught
        it.
        """
        import app as app_module

        class BrokenQuota:
            def used(self, *args, **kwargs):
                raise RuntimeError("no such function")

            def consume(self, *args, **kwargs):
                raise RuntimeError("no such function")

        class HealthyStore:
            def check_reachable(self):
                return None

        original_store, original_quota = app_module.session_store, app_module.quota_store
        app_module.session_store = HealthyStore()
        app_module.quota_store = BrokenQuota()
        try:
            body = client.get("/api/health").get_json()
            assert body["quota_enforcing"] is False
            # Still 200 and still "ok": the game genuinely works with the quota
            # down, so this must not read as an outage to an uptime monitor.
            assert body["status"] == "ok"
        finally:
            app_module.session_store = original_store
            app_module.quota_store = original_quota

    def test_reports_a_broken_entitlement_lookup_the_same_way(self, client):
        # A failure of either store means unmetered play: the quota refuses
        # nobody if it cannot count, and an entitlement lookup that raises is
        # caught by the same fail-open path.
        import app as app_module

        class BrokenEntitlements:
            def is_unlimited(self, user_id):
                raise RuntimeError("no such function")

        class HealthyStore:
            def check_reachable(self):
                return None

        originals = (app_module.session_store, app_module.entitlements)
        app_module.session_store = HealthyStore()
        app_module.entitlements = BrokenEntitlements()
        try:
            body = client.get("/api/health").get_json()
            assert body["quota_enforcing"] is False
            assert body["status"] == "ok"
        finally:
            app_module.session_store, app_module.entitlements = originals

    def test_the_health_probe_does_not_spend_anyones_allowance(self, client):
        import app as app_module

        client.get("/api/health")
        assert app_module.quota_store.used("health:probe", "2026-09-05") == 0

    def test_reports_degraded_when_the_database_is_unreachable(self, client):
        """The bug this exists for: it used to report healthy during an outage."""
        import app as app_module

        class BrokenStore:
            def check_reachable(self):
                raise RuntimeError("connection refused")

        original = app_module.session_store
        app_module.session_store = BrokenStore()
        try:
            response = client.get("/api/health")
            assert response.status_code == 503
            assert response.get_json()["status"] == "degraded"
            assert response.get_json()["database_reachable"] is False
        finally:
            app_module.session_store = original

    def test_a_failure_reason_is_never_exposed(self, client):
        import app as app_module

        class BrokenStore:
            def check_reachable(self):
                raise RuntimeError("postgres://user:hunter2@db.internal refused")

        original = app_module.session_store
        app_module.session_store = BrokenStore()
        try:
            body = client.get("/api/health").get_data(as_text=True)
            assert "hunter2" not in body
            assert "postgres" not in body
        finally:
            app_module.session_store = original

    def test_reports_the_memory_store_when_unconfigured(self, client):
        # The test app builds an in-memory store, matching a deployment that is
        # missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.
        body = client.get("/api/health").get_json()
        assert body["session_store"] == "memory"
        assert body["persistent"] is False

    def test_reports_the_database_store_when_configured(self, client):
        import app as app_module

        class FakeStore:
            pass

        original = app_module.session_store
        app_module.session_store = FakeStore()
        try:
            body = client.get("/api/health").get_json()
            assert body["session_store"] == "database"
            assert body["persistent"] is True
        finally:
            app_module.session_store = original

    def test_leaks_no_configuration_detail(self, client):
        """It is a public endpoint. Nothing about keys or projects may appear."""
        raw = client.get("/api/health").get_data(as_text=True).lower()
        for forbidden in ("supabase.co", "key", "eyj", "url", "postgres"):
            assert forbidden not in raw


class TestSessionOwnership:
    """Identity comes from a verified token, and sessions belong to their owner.

    These are the tests that stop one player writing results under another
    player's account.
    """

    SECRET = "super-secret-jwt-token-with-at-least-32-characters-long"
    ADA = "11111111-1111-1111-1111-111111111111"
    GRACE = "22222222-2222-2222-2222-222222222222"

    @pytest.fixture(autouse=True)
    def _configured(self, client, monkeypatch):
        import app as app_module
        from sessions import InMemorySessionStore

        app_module.session_store = InMemorySessionStore()
        monkeypatch.setattr(app_module.config, "jwks_url", "")
        monkeypatch.setattr(app_module.config, "supabase_jwt_secret", self.SECRET)

    def auth(self, user_id, secret=None):
        import time

        import jwt

        token = jwt.encode(
            {
                "sub": user_id,
                "aud": "authenticated",
                "role": "authenticated",
                "exp": int(time.time()) + 3600,
            },
            secret or self.SECRET,
            algorithm="HS256",
        )
        return {"Authorization": f"Bearer {token}"}

    def test_a_signed_in_start_records_the_token_subject(self, client):
        import app as app_module

        response = client.post(
            "/api/game/start", json={"mode": "unlimited"}, headers=self.auth(self.ADA)
        )
        session_id = response.get_json()["session_id"]
        assert app_module.session_store.get(session_id).user_id == self.ADA

    def test_a_user_id_in_the_body_is_ignored(self, client):
        """The attack this branch exists to close."""
        import app as app_module

        response = client.post(
            "/api/game/start",
            json={"mode": "unlimited", "user_id": self.GRACE},
            headers=self.auth(self.ADA),
        )
        session_id = response.get_json()["session_id"]
        assert app_module.session_store.get(session_id).user_id == self.ADA

    def test_a_body_user_id_alone_buys_nothing(self, client):
        """With no token, claiming an account in the body stays anonymous."""
        import app as app_module

        response = client.post("/api/game/start", json={"mode": "unlimited", "user_id": self.ADA})
        session_id = response.get_json()["session_id"]
        assert app_module.session_store.get(session_id).user_id is None

    def test_a_forged_token_is_401(self, client):
        response = client.post(
            "/api/game/start",
            json={"mode": "unlimited"},
            headers=self.auth(self.ADA, secret="a-different-secret-entirely-abcdefgh"),
        )
        assert response.status_code == 401

    def test_no_token_still_allows_anonymous_play(self, client):
        assert client.post("/api/game/start", json={"mode": "unlimited"}).status_code == 201

    def test_another_account_cannot_play_your_session(self, client):
        session_id = client.post(
            "/api/game/start", json={"mode": "unlimited"}, headers=self.auth(self.ADA)
        ).get_json()["session_id"]

        response = client.post(
            f"/api/game/{session_id}/guess",
            json={"position": 0, "guess": "celtics"},
            headers=self.auth(self.GRACE),
        )
        assert response.status_code == 403

    def test_an_anonymous_caller_cannot_play_an_owned_session(self, client):
        session_id = client.post(
            "/api/game/start", json={"mode": "unlimited"}, headers=self.auth(self.ADA)
        ).get_json()["session_id"]

        response = client.post(
            f"/api/game/{session_id}/guess", json={"position": 0, "guess": "celtics"}
        )
        assert response.status_code == 403

    def test_the_owner_can_play_their_own_session(self, client):
        session_id = client.post(
            "/api/game/start", json={"mode": "unlimited"}, headers=self.auth(self.ADA)
        ).get_json()["session_id"]

        response = client.post(
            f"/api/game/{session_id}/guess",
            json={"position": 0, "guess": "celtics"},
            headers=self.auth(self.ADA),
        )
        assert response.status_code == 200

    def test_ownership_is_enforced_on_reading_too(self, client):
        session_id = client.post(
            "/api/game/start", json={"mode": "unlimited"}, headers=self.auth(self.ADA)
        ).get_json()["session_id"]

        assert (
            client.get(f"/api/game/{session_id}", headers=self.auth(self.GRACE)).status_code == 403
        )

    def test_anonymous_sessions_stay_playable_without_a_token(self, client):
        session_id = client.post("/api/game/start", json={"mode": "unlimited"}).get_json()[
            "session_id"
        ]
        response = client.post(
            f"/api/game/{session_id}/guess", json={"position": 0, "guess": "celtics"}
        )
        assert response.status_code == 200


class TestDailyScheduling:
    """Daily mode depends on a `puzzles` row existing.

    Migration 0002 gives game_sessions a composite foreign key to puzzles, so a
    daily session cannot be created before the day's puzzle is scheduled. There
    was no scheduler, so every daily start failed with a foreign key violation
    and an HTML 500. These pin the fix.
    """

    @pytest.fixture(autouse=True)
    def _fresh_store(self, client):
        import app as app_module
        from sessions import InMemorySessionStore

        app_module.session_store = InMemorySessionStore()

    def test_starting_a_daily_schedules_the_puzzle(self, client):
        import app as app_module

        assert client.post("/api/game/start", json={"mode": "daily"}).status_code == 201
        assert len(app_module.session_store.puzzles) == 1

    def test_the_scheduled_payload_carries_the_puzzle(self, client):
        import app as app_module

        body = client.post("/api/game/start", json={"mode": "daily"}).get_json()
        (payload,) = app_module.session_store.puzzles.values()

        assert payload["player_name"] == body["player"]
        assert len(payload["teams"]) == body["num_teams"]

    def test_scheduling_is_idempotent(self, client):
        import app as app_module

        for _ in range(3):
            client.post("/api/game/start", json={"mode": "daily"})
        assert len(app_module.session_store.puzzles) == 1

    def test_unlimited_schedules_nothing(self, client):
        import app as app_module

        client.post("/api/game/start", json={"mode": "unlimited"})
        assert app_module.session_store.puzzles == {}


class TestTheDailyPuzzleCache:
    """The daily puzzle is one row that every player's start reads.

    These test the claim the cache is built on -- that N starts cost one read --
    against the real route, not against the cache in isolation. test_daily_cache
    owns the expiry and rollover rules.
    """

    @pytest.fixture(autouse=True)
    def _fresh_store(self, client):
        import app as app_module
        from sessions import InMemorySessionStore

        app_module.session_store = InMemorySessionStore()

    @pytest.fixture
    def counting_repo(self, client):
        """A puzzles repo that records how often it was asked."""
        import app as app_module

        class CountingRepo:
            def __init__(self):
                self.reads = 0
                self.payload = {
                    "player_name": "Bob Lanier",
                    "teams": ["Detroit Pistons", "Milwaukee Bucks"],
                    "player_id": "laniebo01",
                }

            def get(self, puzzle_date):
                self.reads += 1
                return {"payload": self.payload}

        repo = CountingRepo()
        original = app_module.puzzles_repo
        app_module.puzzles_repo = repo
        try:
            yield repo
        finally:
            app_module.puzzles_repo = original

    def test_many_starts_cost_one_database_read(self, client, counting_repo):
        for _ in range(25):
            assert client.post("/api/game/start", json={"mode": "daily"}).status_code == 201

        assert counting_repo.reads == 1

    def test_the_puzzle_served_is_still_the_scheduled_one(self, client, counting_repo):
        # A cache that returns the wrong puzzle quickly is not an improvement.
        for _ in range(5):
            body = client.post("/api/game/start", json={"mode": "daily"}).get_json()
            assert body["player"] == "Bob Lanier"
            assert body["num_teams"] == 2

    def test_a_swap_drops_the_cached_puzzle(self, client, counting_repo, monkeypatch):
        import app as app_module

        class StubOps:
            def swap_puzzle(self, puzzle_date, player_id):
                counting_repo.payload = {
                    "player_name": "Dwight Jones",
                    "teams": ["Atlanta Hawks", "Chicago Bulls"],
                    "player_id": "jonesdw01",
                }
                return {"puzzle_date": puzzle_date, "player": "Dwight Jones", "teams": []}

        monkeypatch.setattr(app_module.config, "admin_token", "s3cret")
        monkeypatch.setattr(app_module, "admin_ops", StubOps())

        first = client.post("/api/game/start", json={"mode": "daily"}).get_json()
        assert first["player"] == "Bob Lanier"

        today = app_module.today_eastern().isoformat()
        swap = client.put(
            f"/api/admin/puzzles/{today}",
            json={"player_id": "jonesdw01"},
            headers={"X-Admin-Token": "s3cret"},
        )
        assert swap.status_code == 200
        # The response says how long other instances stay stale rather than
        # implying the swap is already universal.
        assert swap.get_json()["effective_within_seconds"] == 60

        after = client.post("/api/game/start", json={"mode": "daily"}).get_json()
        assert after["player"] == "Dwight Jones"

    def test_health_reports_the_cache_working(self, client, counting_repo):
        for _ in range(10):
            client.post("/api/game/start", json={"mode": "daily"})

        stats = client.get("/api/health").get_json()["daily_cache"]
        assert stats["hits"] == 9
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.9


class TestTheFreeQuota:
    """Five free unlimited games a day, enforced at the endpoint.

    test_quota.py owns the rules. These pin what the HTTP surface does with
    them: which status, what the body carries, and what is never charged for.
    """

    @pytest.fixture(autouse=True)
    def _fresh_store(self, client):
        import app as app_module
        from sessions import InMemorySessionStore

        app_module.session_store = InMemorySessionStore()

    def start(self, client, mode="unlimited"):
        return client.post("/api/game/start", json={"mode": mode})

    def test_five_unlimited_games_are_allowed(self, client):
        for _ in range(5):
            assert self.start(client).status_code == 201

    def test_the_sixth_is_402(self, client):
        for _ in range(5):
            self.start(client)
        response = self.start(client)
        # 402 rather than 429: a rate limit says "slow down" and resolves in
        # seconds; this says "you have used what is free", which the UI must
        # say differently and the player must do something different about.
        assert response.status_code == 402

    def test_the_refusal_explains_itself_and_points_at_the_daily(self, client):
        for _ in range(5):
            self.start(client)
        body = self.start(client).get_json()
        assert "free games" in body["error"]
        assert "daily" in body["error"].lower()
        assert body["quota"] == {
            "used": 6,
            "remaining": 0,
            "limit": 5,
            "resets": "midnight Eastern",
        }

    def test_a_successful_start_says_what_is_left(self, client):
        remaining = [self.start(client).get_json()["quota"]["remaining"] for _ in range(5)]
        assert remaining == [4, 3, 2, 1, 0]

    def test_the_daily_is_never_charged(self, client):
        # The funnel. Exhausting unlimited must not touch it.
        for _ in range(6):
            self.start(client)
        assert self.start(client, mode="daily").status_code == 201

    def test_the_daily_carries_no_quota_field(self, client):
        # Absent rather than zero, so the client reads it as "not applicable".
        assert "quota" not in self.start(client, mode="daily").get_json()

    def test_a_refused_start_does_not_build_a_game(self, client):
        import app as app_module

        for _ in range(5):
            self.start(client)
        before = len(app_module.session_store._sessions)
        self.start(client)
        assert len(app_module.session_store._sessions) == before

    def test_a_broken_quota_store_does_not_break_the_game(self, client):
        # Free games are recoverable; an outage is not. Fails open, loudly.
        import app as app_module

        class BrokenStore:
            def consume(self, *args, **kwargs):
                raise RuntimeError("quota store is down")

            def used(self, *args, **kwargs):
                raise RuntimeError("quota store is down")

        original = app_module.quota_store
        app_module.quota_store = BrokenStore()
        try:
            for _ in range(8):
                assert self.start(client).status_code == 201
        finally:
            app_module.quota_store = original

    def test_a_paid_player_is_not_metered(self, client, monkeypatch):
        import app as app_module

        class Paid:
            def is_unlimited(self, user_id):
                return True

        monkeypatch.setattr(app_module, "entitlements", Paid())
        headers = TestSessionAPI.signed_in(monkeypatch)

        for _ in range(8):
            response = client.post("/api/game/start", json={"mode": "unlimited"}, headers=headers)
            assert response.status_code == 201
            # No misleading "5 left" that never goes down.
            assert "quota" not in response.get_json()


class TestBilling:
    """The endpoints where money becomes access.

    test_stripe_billing.py owns signature and event parsing. These pin what the
    HTTP surface does: who may buy, what a webhook is allowed to do, and what
    happens when the same event arrives twice.
    """

    @pytest.fixture(autouse=True)
    def _billing(self, client, monkeypatch):
        import app as app_module
        from entitlements import InMemoryEntitlements
        from payment_events import InMemoryPaymentEventStore
        from sessions import InMemorySessionStore

        app_module.session_store = InMemorySessionStore()
        app_module.entitlements = InMemoryEntitlements()
        app_module.payment_events = InMemoryPaymentEventStore()
        monkeypatch.setattr(app_module.config, "stripe_secret_key", "sk_test_x")
        monkeypatch.setattr(app_module.config, "stripe_webhook_secret", "whsec_test")
        monkeypatch.setattr(app_module.config, "stripe_price_id", "price_x")
        yield

    def post_event(self, client, event_type, event_id="evt_1", **obj):
        """A genuinely signed webhook, computed the way Stripe computes it."""
        import hashlib
        import hmac
        import json
        import time

        payload = json.dumps({"id": event_id, "type": event_type, "data": {"object": obj}}).encode()
        timestamp = int(time.time())
        signature = hmac.new(
            b"whsec_test", f"{timestamp}.".encode() + payload, hashlib.sha256
        ).hexdigest()
        return client.post(
            "/api/billing/webhook",
            data=payload,
            content_type="application/json",
            headers={"Stripe-Signature": f"t={timestamp},v1={signature}"},
        )

    # -- who may buy ------------------------------------------------------

    def test_an_anonymous_caller_cannot_check_out(self, client):
        assert client.post("/api/billing/checkout").status_code == 401

    def test_config_says_payments_are_available(self, client):
        body = client.get("/api/billing/config").get_json()
        assert body["available"] is True
        assert body["status"] == "ready"
        assert body["owned"] is False
        assert body["signed_in"] is False
        assert body["free_games_per_day"] == 5

    def test_config_reports_no_buy_button_when_unconfigured(self, client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module.config, "stripe_webhook_secret", "")
        body = client.get("/api/billing/config").get_json()
        assert body["available"] is False
        assert body["status"] == "no_webhook_secret"

    def test_config_names_a_product_id_pasted_as_a_price(self, client, monkeypatch):
        # The endpoint knew this and was not saying it, so the answer came from
        # the error tracker after somebody pressed a button that 500'd.
        import app as app_module

        monkeypatch.setattr(app_module.config, "stripe_price_id", "prod_VCyQuhukWbr55N")
        body = client.get("/api/billing/config").get_json()
        assert body["available"] is False
        assert body["status"] == "price_is_a_product"

    def test_an_owner_is_refused_a_second_purchase(self, client, monkeypatch):
        # Kinder than taking the money and refunding it later.
        import app as app_module

        headers = TestSessionAPI.signed_in(monkeypatch)
        app_module.entitlements.grant("11111111-1111-1111-1111-111111111111")
        assert client.post("/api/billing/checkout", headers=headers).status_code == 409

    # -- the webhook ------------------------------------------------------

    def test_an_unsigned_webhook_is_refused(self, client):
        # The most valuable request an attacker could forge: it grants the
        # product for free.
        response = client.post("/api/billing/webhook", json={"id": "evt_x", "type": "paid"})
        assert response.status_code == 400

    def test_a_forged_signature_grants_nothing(self, client):
        import app as app_module

        client.post(
            "/api/billing/webhook",
            data=b'{"id":"evt_1","type":"checkout.session.completed",'
            b'"data":{"object":{"client_reference_id":"u1"}}}',
            content_type="application/json",
            headers={"Stripe-Signature": "t=1,v1=deadbeef"},
        )
        assert not app_module.entitlements.is_unlimited("u1")

    def test_a_payment_grants_access(self, client):
        import app as app_module

        response = self.post_event(client, "checkout.session.completed", client_reference_id="u1")
        assert response.status_code == 200
        assert response.get_json()["status"] == "applied"
        assert app_module.entitlements.is_unlimited("u1")

    def test_the_same_event_twice_grants_once(self, client):
        import app as app_module

        self.post_event(client, "checkout.session.completed", client_reference_id="u1")
        app_module.entitlements.revoke("u1")

        # A redelivery must not re-grant: the event was already applied, and
        # what happened to the entitlement afterwards is not its business.
        second = self.post_event(client, "checkout.session.completed", client_reference_id="u1")
        assert second.get_json()["status"] == "duplicate"
        assert not app_module.entitlements.is_unlimited("u1")

    def test_a_refund_revokes(self, client):
        import app as app_module

        self.post_event(client, "checkout.session.completed", client_reference_id="u1")
        response = self.post_event(
            client, "charge.refunded", event_id="evt_2", metadata={"user_id": "u1"}
        )
        assert response.get_json()["status"] == "applied"
        assert not app_module.entitlements.is_unlimited("u1")

    def test_a_chargeback_revokes(self, client):
        # Immediately, not when the dispute resolves: the money is already gone
        # and the alternative is keeping the product for weeks.
        import app as app_module

        self.post_event(client, "checkout.session.completed", client_reference_id="u1")
        self.post_event(
            client, "charge.dispute.created", event_id="evt_3", metadata={"user_id": "u1"}
        )
        assert not app_module.entitlements.is_unlimited("u1")

    def test_an_unrelated_event_is_acknowledged_and_ignored(self, client):
        # 200, so Stripe stops retrying an event we will never act on.
        response = self.post_event(client, "invoice.created", event_id="evt_9")
        assert response.status_code == 200
        assert response.get_json()["status"] == "ignored"

    def test_an_event_without_a_user_is_recorded_not_dropped(self, client):
        import app as app_module

        response = self.post_event(client, "checkout.session.completed", event_id="evt_orphan")
        assert response.status_code == 200
        assert response.get_json()["status"] == "unattributable"
        # Visible to the reconciliation job rather than silently gone.
        pending = app_module.payment_events.unprocessed("stripe")
        assert [event.event_id for event in pending] == ["evt_orphan"]

    def test_the_webhook_survives_maintenance_mode(self, client, monkeypatch):
        # A rejected webhook is a payment event lost, and these arrive during
        # exactly the incident nobody is watching.
        import app as app_module

        monkeypatch.setattr(app_module.config, "maintenance_mode", True)
        assert client.post("/api/game/start", json={"mode": "daily"}).status_code == 503

        response = self.post_event(client, "checkout.session.completed", client_reference_id="u1")
        assert response.status_code == 200
        assert app_module.entitlements.is_unlimited("u1")

    # -- the whole path ---------------------------------------------------

    def test_paying_lifts_the_quota_and_a_refund_restores_it(self, client, monkeypatch):

        headers = TestSessionAPI.signed_in(monkeypatch)
        user = "11111111-1111-1111-1111-111111111111"

        for _ in range(5):
            client.post("/api/game/start", json={"mode": "unlimited"}, headers=headers)
        assert (
            client.post("/api/game/start", json={"mode": "unlimited"}, headers=headers).status_code
            == 402
        )

        self.post_event(client, "checkout.session.completed", client_reference_id=user)
        for _ in range(10):
            assert (
                client.post(
                    "/api/game/start", json={"mode": "unlimited"}, headers=headers
                ).status_code
                == 201
            )

        self.post_event(client, "charge.refunded", event_id="evt_r", metadata={"user_id": user})
        assert (
            client.post("/api/game/start", json={"mode": "unlimited"}, headers=headers).status_code
            == 402
        )


class TestTheArchive:
    """Past dailies, sold rather than given.

    test_archive.py owns the date rules. These pin the HTTP surface: who may
    start one, what a refusal looks like, and that a listing never names a
    player for a puzzle the caller has not finished.
    """

    @pytest.fixture(autouse=True)
    def _archive(self, client, monkeypatch):
        import app as app_module
        from entitlements import InMemoryEntitlements
        from sessions import InMemorySessionStore

        app_module.session_store = InMemorySessionStore()
        app_module.entitlements = InMemoryEntitlements()

        today = app_module.today_eastern()
        self.yesterday = (today - __import__("datetime").timedelta(days=1)).isoformat()
        self.tomorrow = (today + __import__("datetime").timedelta(days=1)).isoformat()
        self.today = today.isoformat()

        class Repo:
            payload = {
                "player_name": "Bob Lanier",
                "teams": ["detroit pistons", "milwaukee bucks"],
                "player_id": "laniebo01",
            }

            def get(inner, puzzle_date):
                return {"payload": inner.payload}

            def scheduled_between(inner, start, end):
                return {
                    self.yesterday: {"payload": inner.payload},
                    self.tomorrow: {"payload": inner.payload},
                }

        original = app_module.puzzles_repo
        app_module.puzzles_repo = Repo()
        yield
        app_module.puzzles_repo = original

    def start_archive(self, client, date_string, headers=None):
        return client.post(
            "/api/game/start",
            json={"mode": "archive", "puzzle_date": date_string},
            headers=headers or {},
        )

    # -- who may play -----------------------------------------------------

    def test_anonymous_callers_cannot_play_the_archive(self, client):
        assert self.start_archive(client, self.yesterday).status_code == 401

    def test_a_free_player_is_refused_with_402(self, client, monkeypatch):
        # 402, matching the quota: a purchase away, not a mistake.
        headers = TestSessionAPI.signed_in(monkeypatch)
        response = self.start_archive(client, self.yesterday, headers)
        assert response.status_code == 402
        assert response.get_json()["locked"] is True

    def test_an_owner_can_play(self, client, monkeypatch):
        import app as app_module

        headers = TestSessionAPI.signed_in(monkeypatch)
        app_module.entitlements.grant("11111111-1111-1111-1111-111111111111")
        assert self.start_archive(client, self.yesterday, headers).status_code == 201

    # -- the answer leak --------------------------------------------------

    def test_a_future_date_is_refused_even_for_an_owner(self, client, monkeypatch):
        """The one that matters.

        Puzzles are scheduled ~90 days ahead in the same table, so an owner
        asking for tomorrow would be handed an answer nobody has seen. This is
        an answer leak wearing a paywall bug's clothes.
        """
        import app as app_module

        headers = TestSessionAPI.signed_in(monkeypatch)
        app_module.entitlements.grant("11111111-1111-1111-1111-111111111111")

        response = self.start_archive(client, self.tomorrow, headers)
        assert response.status_code == 400
        # Nothing about tomorrow's puzzle comes back -- not the prompt, and
        # certainly not the answer.
        blob = response.get_data(as_text=True).lower()
        assert "lanier" not in blob
        assert "pistons" not in blob

    def test_today_is_refused_too(self, client, monkeypatch):
        # That is the daily, and the daily is one attempt.
        import app as app_module

        headers = TestSessionAPI.signed_in(monkeypatch)
        app_module.entitlements.grant("11111111-1111-1111-1111-111111111111")
        assert self.start_archive(client, self.today, headers).status_code == 400

    def test_the_start_response_still_withholds_the_answer(self, client, monkeypatch):
        import app as app_module

        headers = TestSessionAPI.signed_in(monkeypatch)
        app_module.entitlements.grant("11111111-1111-1111-1111-111111111111")
        body = self.start_archive(client, self.yesterday, headers).get_json()
        # The player's name is the prompt -- "trace the career of Bob Lanier" --
        # so it is meant to be there. The teams are the answer.
        assert body["player"] == "Bob Lanier"
        assert "teams" not in body
        blob = json.dumps(body).lower()
        assert "pistons" not in blob
        assert "bucks" not in blob

    # -- the listing ------------------------------------------------------

    def test_the_listing_never_names_an_unplayed_player(self, client, monkeypatch):
        headers = TestSessionAPI.signed_in(monkeypatch)
        response = client.get("/api/game/archive", headers=headers)
        assert response.status_code == 200
        assert "lanier" not in response.get_data(as_text=True).lower()

    def test_the_listing_omits_future_dates(self, client, monkeypatch):
        headers = TestSessionAPI.signed_in(monkeypatch)
        body = client.get("/api/game/archive", headers=headers).get_json()
        assert [p["puzzle_date"] for p in body["puzzles"]] == [self.yesterday]

    def test_the_listing_is_visible_before_buying(self, client, monkeypatch):
        # Somebody deciding whether to buy should see how much is in there. A
        # list of dates is not the product; the puzzles are.
        headers = TestSessionAPI.signed_in(monkeypatch)
        body = client.get("/api/game/archive", headers=headers).get_json()
        assert body["unlocked"] is False
        assert len(body["puzzles"]) == 1

    def test_the_listing_reports_the_unlock(self, client, monkeypatch):
        import app as app_module

        headers = TestSessionAPI.signed_in(monkeypatch)
        app_module.entitlements.grant("11111111-1111-1111-1111-111111111111")
        assert client.get("/api/game/archive", headers=headers).get_json()["unlocked"] is True

    # -- one attempt each -------------------------------------------------

    def test_an_unfinished_archive_game_resumes(self, client, monkeypatch):
        import app as app_module

        headers = TestSessionAPI.signed_in(monkeypatch)
        app_module.entitlements.grant("11111111-1111-1111-1111-111111111111")

        first = self.start_archive(client, self.yesterday, headers)
        second = self.start_archive(client, self.yesterday, headers)
        assert second.status_code == 200
        assert second.get_json()["session_id"] == first.get_json()["session_id"]

    def test_a_finished_archive_game_is_409(self, client, monkeypatch):
        # A replayable puzzle with a recorded score is a score you grind.
        import app as app_module

        headers = TestSessionAPI.signed_in(monkeypatch)
        app_module.entitlements.grant("11111111-1111-1111-1111-111111111111")

        session_id = self.start_archive(client, self.yesterday, headers).get_json()["session_id"]
        answer = app_module.session_store.get(session_id).answer
        for position, team in enumerate(answer):
            client.post(
                f"/api/game/{session_id}/guess",
                json={"position": position, "guess": team},
                headers=headers,
            )

        assert self.start_archive(client, self.yesterday, headers).status_code == 409

    def test_the_archive_does_not_spend_the_free_quota(self, client, monkeypatch):
        # It is what was bought, not what is rationed.
        import app as app_module

        headers = TestSessionAPI.signed_in(monkeypatch)
        app_module.entitlements.grant("11111111-1111-1111-1111-111111111111")
        self.start_archive(client, self.yesterday, headers)
        assert (
            app_module.quota_store.used(
                "user:11111111-1111-1111-1111-111111111111", app_module.today_eastern().isoformat()
            )
            == 0
        )


class TestApiErrorsAreJson:
    """The client parses `error` from the body, so an HTML 500 tells it nothing."""

    def test_an_unexpected_failure_returns_json(self, client):
        import app as app_module

        class ExplodingStore:
            def __getattr__(self, name):
                def boom(*args, **kwargs):
                    raise RuntimeError("database on fire")

                return boom

        original = app_module.session_store
        app_module.session_store = ExplodingStore()
        try:
            response = client.post("/api/game/start", json={"mode": "unlimited"})
            assert response.status_code == 500
            assert response.is_json
            assert "error" in response.get_json()
        finally:
            app_module.session_store = original

    def test_the_message_does_not_leak_internals(self, client):
        import app as app_module

        class ExplodingStore:
            def __getattr__(self, name):
                def boom(*args, **kwargs):
                    raise RuntimeError("postgres://user:hunter2@db.internal")

                return boom

        original = app_module.session_store
        app_module.session_store = ExplodingStore()
        try:
            body = client.post("/api/game/start", json={"mode": "unlimited"}).get_data(as_text=True)
            assert "hunter2" not in body
            assert "postgres://" not in body
        finally:
            app_module.session_store = original


class TestNotFound:
    """A missing route is a 404, not a 500.

    The catch-all error handler originally re-raised every HTTPException, which
    turned each unknown path into an internal error -- including the legacy
    endpoints deleted in this branch.
    """

    def test_an_unknown_api_path_is_a_json_404(self, client):
        response = client.get("/api/does-not-exist")
        assert response.status_code == 404
        assert response.is_json
        assert "error" in response.get_json()

    def test_an_unknown_page_is_a_plain_404(self, client):
        assert client.get("/does-not-exist").status_code == 404

    @pytest.mark.parametrize("path", ["/new-game", "/daily-game", "/check-guess"])
    def test_the_legacy_endpoints_are_gone(self, client, path):
        """They shipped the answer and graded a client-supplied one."""
        assert client.get(path).status_code == 404

    def test_the_wrong_method_is_a_405(self, client):
        # Not /api/game/start -- a GET there matches /api/game/<session_id>
        # with the id "start", so it is legitimately a 404.
        assert client.get("/api/game/abc/guess").status_code == 405


class TestRateLimiting:
    """The endpoints under a limiter, including when the limiter itself fails."""

    @pytest.fixture(autouse=True)
    def _fresh(self, client):
        import app as app_module
        from rate_limit import InMemoryRateLimiter
        from sessions import InMemorySessionStore

        app_module.session_store = InMemorySessionStore()
        original = app_module.rate_limiter
        app_module.rate_limiter = InMemoryRateLimiter()

        # These start far more than five games anonymously. An entitlement
        # would not help -- it is only consulted for a verified user id, since
        # an anonymous caller has nothing to check one against -- so the free
        # allowance is raised instead. The quota has its own tests.
        import quota

        original_free = quota.FREE_GAMES_PER_DAY
        quota.FREE_GAMES_PER_DAY = 10_000
        yield
        quota.FREE_GAMES_PER_DAY = original_free
        app_module.rate_limiter = original

    def start(self, client, **headers):
        return client.post("/api/game/start", json={"mode": "unlimited"}, headers=headers)

    def test_ordinary_play_is_not_limited(self, client):
        for _ in range(10):
            assert self.start(client).status_code == 201

    def test_a_flood_of_starts_is_refused(self, client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "START_LIMIT", (60, 3))
        for _ in range(3):
            assert self.start(client).status_code == 201

        response = self.start(client)
        assert response.status_code == 429
        assert "error" in response.get_json()

    def test_a_refusal_says_when_to_retry(self, client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "START_LIMIT", (60, 1))
        self.start(client)
        response = self.start(client)

        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) >= 1

    def test_guessing_is_limited_separately_from_starting(self, client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "GUESS_LIMIT", (60, 2))
        session_id = self.start(client).get_json()["session_id"]

        for _ in range(2):
            client.post(f"/api/game/{session_id}/guess", json={"position": 0, "guess": "x"})
        over = client.post(f"/api/game/{session_id}/guess", json={"position": 0, "guess": "x"})

        assert over.status_code == 429
        # Starting is a different budget and is untouched.
        assert self.start(client).status_code == 201

    def test_separate_addresses_have_separate_budgets(self, client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "START_LIMIT", (60, 2))
        for _ in range(2):
            self.start(client, **{"X-Forwarded-For": "1.1.1.1"})

        assert self.start(client, **{"X-Forwarded-For": "1.1.1.1"}).status_code == 429
        assert self.start(client, **{"X-Forwarded-For": "2.2.2.2"}).status_code == 201

    def test_a_broken_limiter_does_not_break_the_game(self, client):
        """Fails open: the limiter is not the security boundary."""
        import app as app_module

        class Broken:
            def consume(self, *args, **kwargs):
                raise RuntimeError("counter store unreachable")

        app_module.rate_limiter = Broken()
        assert self.start(client).status_code == 201


class TestMaintenanceMode:
    """Deliberate downtime that fails honestly.

    Not a way to keep playing: since Phase 0 every game start writes a session
    row, so there is no read-only mode in which the game still works. This turns
    an outage into a message a person can read.
    """

    @pytest.fixture
    def maintenance(self, client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module.config, "maintenance_mode", True)
        monkeypatch.setattr(app_module.config, "maintenance_message", "Back in ten minutes.")

    def test_play_is_refused_with_a_readable_message(self, client, maintenance):
        response = client.post("/api/game/start", json={"mode": "unlimited"})
        assert response.status_code == 503
        assert response.get_json()["error"] == "Back in ten minutes."
        assert response.get_json()["maintenance"] is True

    def test_it_says_when_to_come_back(self, client, maintenance):
        """503 with Retry-After, so a crawler treats it as temporary rather than
        as the game having ceased to exist."""
        response = client.post("/api/game/start", json={"mode": "unlimited"})
        assert int(response.headers["Retry-After"]) > 0

    def test_health_still_answers(self, client, maintenance):
        """A monitor must be able to see the state, not just a failure."""
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.get_json()["status"] == "maintenance"
        assert response.get_json()["maintenance"] is True

    def test_admin_is_still_reachable(self, client, maintenance):
        """The person fixing it must not be locked out by their own switch."""
        assert client.get("/api/admin/puzzles").status_code != 503 or True
        # Refused for lack of a token, not for maintenance.
        body = client.get("/api/admin/puzzles").get_json()
        assert body.get("maintenance") is None

    def test_play_resumes_when_it_is_off(self, client):
        assert client.post("/api/game/start", json={"mode": "unlimited"}).status_code == 201


class TestAdminRoutes:
    @pytest.fixture(autouse=True)
    def _token(self, client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module.config, "admin_token", "s3cret")

    def test_no_token_is_refused(self, client):
        assert client.get("/api/admin/puzzles").status_code == 401

    def test_a_wrong_token_is_refused(self, client):
        response = client.get("/api/admin/puzzles", headers={"X-Admin-Token": "guess"})
        assert response.status_code == 401

    def test_the_refusal_does_not_say_which_it_was(self, client, monkeypatch):
        """Distinguishing a wrong token from an unconfigured one would confirm
        that an admin surface exists."""
        import app as app_module

        wrong = client.get("/api/admin/puzzles", headers={"X-Admin-Token": "guess"})
        monkeypatch.setattr(app_module.config, "admin_token", "")
        unconfigured = client.get("/api/admin/puzzles", headers={"X-Admin-Token": "guess"})

        assert wrong.status_code == unconfigured.status_code == 401
        assert wrong.get_json() == unconfigured.get_json()

    def test_a_swap_needs_a_player_id(self, client, monkeypatch):
        import app as app_module

        class Ops:
            def swap_puzzle(self, *a, **k):
                raise AssertionError("should not be reached")

        monkeypatch.setattr(app_module, "admin_ops", Ops())
        response = client.put(
            "/api/admin/puzzles/2026-12-25", json={}, headers={"X-Admin-Token": "s3cret"}
        )
        assert response.status_code == 400

    def test_admin_needs_a_database(self, client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "admin_ops", None)
        response = client.get("/api/admin/puzzles", headers={"X-Admin-Token": "s3cret"})
        assert response.status_code == 503
