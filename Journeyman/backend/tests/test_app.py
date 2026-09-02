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


class TestNewGame:
    def test_returns_the_shape_app_js_destructures(self, client):
        body = client.get("/new-game").get_json()
        assert set(body) == {"Player", "PlayerID", "Teams", "Number of Teams"}
        assert body["Number of Teams"] == len(body["Teams"])

    def test_honours_the_exclude_list(self, client):
        body = client.get("/new-game?exclude=1,2,4").get_json()
        assert body["PlayerID"] == 3

    def test_malformed_exclude_list_does_not_500(self, client):
        # App.js builds this from localStorage, so it is untrusted input.
        assert client.get("/new-game?exclude=abc,,7").status_code == 200

    def test_empty_exclude_param_is_ignored(self, client):
        assert client.get("/new-game?exclude=").status_code == 200


class TestDailyGame:
    def test_includes_the_day_number(self, client):
        body = client.get("/daily-game").get_json()
        assert set(body) == {"Player", "PlayerID", "Teams", "Number of Teams", "DayNumber"}
        assert body["DayNumber"] >= 1

    def test_is_the_same_puzzle_on_repeat_requests(self, client):
        assert client.get("/daily-game").get_json() == client.get("/daily-game").get_json()


class TestCheckGuess:
    def test_grades_a_correct_guess(self, client):
        response = client.post(
            "/check-guess",
            json={"guess": "celtics", "teams": ["boston celtics", "miami heat"], "position": 0},
        )
        assert response.get_json() == {"result": "green"}

    def test_grades_a_misplaced_guess(self, client):
        response = client.post(
            "/check-guess",
            json={"guess": "celtics", "teams": ["boston celtics", "miami heat"], "position": 1},
        )
        assert response.get_json() == {"result": "yellow"}

    def test_grades_a_wrong_guess(self, client):
        response = client.post(
            "/check-guess",
            json={"guess": "lakers", "teams": ["boston celtics", "miami heat"], "position": 0},
        )
        assert response.get_json() == {"result": "gray"}

    def test_grades_regardless_of_casing(self, client):
        response = client.post(
            "/check-guess",
            json={"guess": "Celtics", "teams": ["boston celtics", "miami heat"], "position": 0},
        )
        assert response.get_json() == {"result": "green"}

    @pytest.mark.parametrize(
        "payload",
        [
            {"guess": "celtics", "teams": ["boston celtics"], "position": -1},
            {"guess": "celtics", "teams": ["boston celtics"], "position": 99},
            {"guess": "celtics", "teams": ["boston celtics"], "position": "0"},
            {"guess": "celtics", "teams": [], "position": 0},
            {"guess": None, "teams": ["boston celtics"], "position": 0},
        ],
        ids=["negative", "past-end", "not-an-int", "empty-teams", "guess-missing"],
    )
    def test_malformed_input_is_a_400_not_a_500(self, client, payload):
        response = client.post("/check-guess", json=payload)
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_the_answer_is_supplied_by_the_caller(self, client):
        """The vulnerability, written down.

        The endpoint holds no state: it grades whatever `teams` the caller sends.
        A client can therefore submit an answer it invented and be told it is
        correct. This test should be deleted -- not fixed -- when Phase 0 moves
        the answer server-side behind a session id.
        """
        response = client.post(
            "/check-guess",
            json={"guess": "anything", "teams": ["anything"], "position": 0},
        )
        assert response.get_json() == {"result": "green"}


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

    def test_a_second_daily_for_the_same_user_is_409(self, client):
        first = client.post("/api/game/start", json={"mode": "daily", "user_id": "u1"})
        assert first.status_code == 201

        second = client.post("/api/game/start", json={"mode": "daily", "user_id": "u1"})
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
