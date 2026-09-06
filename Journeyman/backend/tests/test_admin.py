"""Operator tools and the maintenance switch.

The admin token is a real credential guarding operations that change what every
player sees, so the tests that matter are the ones about it being closed.
"""

import pytest
from admin import AdminError, AdminOperations, is_authorised, token_from_headers


class TestAuthorisation:
    def test_the_right_token_is_accepted(self):
        assert is_authorised("s3cret", "s3cret")

    def test_the_wrong_token_is_refused(self):
        assert not is_authorised("guess", "s3cret")

    def test_an_unconfigured_token_closes_the_door(self):
        """Unset must mean nobody, not everybody.

        The opposite default is how an admin endpoint ends up reachable on a
        deployment that never meant to enable one.
        """
        assert not is_authorised("anything", "")
        assert not is_authorised("anything", None)

    def test_an_empty_supplied_token_is_refused(self):
        assert not is_authorised("", "s3cret")
        assert not is_authorised(None, "s3cret")

    def test_a_prefix_is_not_enough(self):
        assert not is_authorised("s3c", "s3cret")

    def test_it_is_read_from_a_dedicated_header(self):
        """Not Authorization, which already carries a player's Supabase token."""
        assert token_from_headers({"X-Admin-Token": "abc"}) == "abc"
        assert token_from_headers({"x-admin-token": "abc"}) == "abc"
        assert token_from_headers({"Authorization": "Bearer abc"}) is None

    def test_a_missing_header_yields_nothing(self):
        assert token_from_headers({}) is None


class FakeTable:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.upserted = None

    def select(self, *_):
        return self

    def eq(self, *_):
        return self

    def gte(self, *_):
        return self

    def lte(self, *_):
        return self

    def order(self, *_):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        return type("R", (), {"data": self.rows})()

    def upsert(self, row, **_):
        self.upserted = row
        return self


class FakeClient:
    def __init__(self, tables=None, rpc_result=0):
        self.tables = tables or {}
        self.rpc_calls = []
        self.rpc_result = rpc_result

    def table(self, name):
        return self.tables.setdefault(name, FakeTable())

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return type("R", (), {"execute": lambda _s: type("D", (), {"data": self.rpc_result})()})()


VALID_PLAYER = {
    "id": "lanieblo01",
    "name": "Bob Lanier",
    "stints": [{"team": "detroit pistons"}, {"team": "milwaukee bucks"}],
}


class TestSwapPuzzle:
    def test_it_rewrites_the_payload_not_just_the_reference(self):
        """The payload is what a session reads; a reference alone changes nothing."""
        client = FakeClient({"players": FakeTable([VALID_PLAYER])})
        result = AdminOperations(client).swap_puzzle("2026-12-25", "lanieblo01")

        written = client.tables["puzzles"].upserted
        assert written["payload"]["player_name"] == "Bob Lanier"
        assert written["payload"]["teams"] == ["detroit pistons", "milwaukee bucks"]
        assert written["puzzle_date"] == "2026-12-25"
        assert result["player"] == "Bob Lanier"

    def test_an_unknown_player_is_refused(self):
        client = FakeClient({"players": FakeTable([])})
        with pytest.raises(AdminError, match="no player"):
            AdminOperations(client).swap_puzzle("2026-12-25", "nobody01")

    def test_a_one_team_career_is_refused(self):
        """Swapping in an unplayable puzzle is worse than the bad one."""
        single = {"id": "x", "name": "One Club", "stints": [{"team": "boston celtics"}]}
        client = FakeClient({"players": FakeTable([single])})
        with pytest.raises(AdminError, match="fewer than two"):
            AdminOperations(client).swap_puzzle("2026-12-25", "x")


class TestVoiding:
    def test_voiding_a_day_reports_how_many_moved(self):
        client = FakeClient(rpc_result=42)
        result = AdminOperations(client).void_day("2026-09-05", reason="bad career data")

        name, params = client.rpc_calls[0]
        assert name == "set_day_voided"
        assert params["p_voided"] is True
        assert params["p_reason"] == "bad career data"
        assert result["voided"] == 42

    def test_restoring_clears_the_flag(self):
        client = FakeClient(rpc_result=42)
        AdminOperations(client).restore_day("2026-09-05")

        _, params = client.rpc_calls[0]
        assert params["p_voided"] is False
        assert params["p_reason"] is None

    def test_voiding_is_reversible(self):
        """Marked, not deleted -- the moment you want it is the moment you are
        least sure it is right."""
        client = FakeClient(rpc_result=1)
        ops = AdminOperations(client)
        ops.void_day("2026-09-05")
        ops.restore_day("2026-09-05")
        assert [params["p_voided"] for _, params in client.rpc_calls] == [True, False]


class TestUpcoming:
    def test_it_summarises_what_is_scheduled(self):
        from datetime import date

        rows = [
            {
                "puzzle_date": "2026-09-06",
                "player_id": "x",
                "payload": {"player_name": "Vince Carter", "teams": ["a", "b", "c"]},
            }
        ]
        client = FakeClient({"puzzles": FakeTable(rows)})
        upcoming = AdminOperations(client).upcoming_puzzles(date(2026, 9, 5), days=7)

        assert upcoming == [{"puzzle_date": "2026-09-06", "player": "Vince Carter", "num_teams": 3}]
