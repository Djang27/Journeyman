"""Endpoint tests against the Flask test client.

Deliberately thin. These check request/response contracts -- the shapes the
frontend depends on -- and leave grading rules to test_game_logic.py.
"""

import pytest


@pytest.fixture
def client(player_db):
    from app import app

    app.config["TESTING"] = True
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

    def test_a_second_daily_for_the_same_user_is_409(self, client, monkeypatch):
        import time

        import app as app_module
        import jwt

        secret = "super-secret-jwt-token-with-at-least-32-characters-long"
        monkeypatch.setattr(app_module.config, "jwks_url", "")
        monkeypatch.setattr(app_module.config, "supabase_jwt_secret", secret)
        token = jwt.encode(
            {
                "sub": "11111111-1111-1111-1111-111111111111",
                "aud": "authenticated",
                "exp": int(time.time()) + 3600,
            },
            secret,
            algorithm="HS256",
        )
        headers = {"Authorization": f"Bearer {token}"}

        assert (
            client.post("/api/game/start", json={"mode": "daily"}, headers=headers).status_code
            == 201
        )

        second = client.post("/api/game/start", json={"mode": "daily"}, headers=headers)
        assert second.status_code == 409

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
            }
        finally:
            app_module.session_store = original

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
        yield
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
