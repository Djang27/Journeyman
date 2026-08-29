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
