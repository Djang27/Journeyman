"""Tests for puzzle selection.

The daily-puzzle tests below are the reason this file exists: they demonstrate
that today's md5-of-the-date selection is coupled to the *size* of the player
pool, so adding a player silently reshuffles every future daily.
"""

import json
from datetime import date, timedelta

import pytest


class TestDayNumber:
    def test_launch_day_is_day_one(self, player_db, frozen_date):
        frozen_date(player_db, 2026, 6, 11)
        assert player_db.day_number() == 1

    def test_counts_forward_from_launch(self, player_db, frozen_date):
        frozen_date(player_db, 2026, 6, 21)
        assert player_db.day_number() == 11


class TestDailyPlayer:
    def test_is_stable_for_a_given_date(self, player_db, frozen_date):
        frozen_date(player_db, 2026, 8, 27)
        first = player_db.daily_player()
        second = player_db.daily_player()
        assert first == second

    def test_returns_a_player_from_the_pool(self, player_db, frozen_date, sample_players):
        frozen_date(player_db, 2026, 8, 27)
        name, teams, player_id, _ = player_db.daily_player()
        match = next(p for p in sample_players if p["id"] == player_id)
        assert (name, teams) == (match["name"], match["teams"])

    def test_includes_the_day_number(self, player_db, frozen_date):
        frozen_date(player_db, 2026, 6, 12)
        *_, day_num = player_db.daily_player()
        assert day_num == 2

    def test_selection_shifts_when_the_pool_grows(
        self, player_db, frozen_date, sample_players, tmp_path
    ):
        """The bug that motivates the daily_puzzles table.

        Selection is `md5(date) % len(players)`, so the pool size is part of the
        key. Adding one player rewrites the schedule for future dates that have
        already been fixed -- including ones players may have already been told
        about. Any individual date may coincidentally survive, so this measures
        the schedule as a whole rather than a single day.
        """
        dates = [date(2026, 9, 1) + timedelta(days=offset) for offset in range(30)]

        def schedule():
            picked = []
            for day in dates:
                frozen_date(player_db, day.year, day.month, day.day)
                picked.append(player_db.daily_player()[2])
            return picked

        before = schedule()

        grown = sample_players + [
            {"id": 999, "name": "New Signing", "ppg": 9.0, "teams": ["miami heat", "utah jazz"]}
        ]
        bigger = tmp_path / "grown.json"
        bigger.write_text(json.dumps({"players": grown}), encoding="utf-8")
        player_db.PLAYER_DATABASE_PATH = bigger

        after = schedule()

        changed = sum(1 for i in range(len(dates)) if before[i] != after[i])
        assert changed > 0, (
            "if this ever passes, the schedule is decoupled from pool size and "
            "the test can be deleted"
        )


class TestRandomPlayer:
    def test_returns_a_player_from_the_pool(self, player_db, sample_players):
        _, _, player_id = player_db.randomPlayer()
        assert player_id in {p["id"] for p in sample_players}

    def test_excludes_seen_ids(self, player_db, sample_players):
        seen = {p["id"] for p in sample_players} - {3}
        for _ in range(20):
            assert player_db.randomPlayer(exclude_ids=seen)[2] == 3

    def test_resets_once_every_player_has_been_seen(self, player_db, sample_players):
        everyone = {p["id"] for p in sample_players}
        _, _, player_id = player_db.randomPlayer(exclude_ids=everyone)
        assert player_id in everyone

    def test_empty_exclude_set_is_ignored(self, player_db, sample_players):
        _, _, player_id = player_db.randomPlayer(exclude_ids=set())
        assert player_id in {p["id"] for p in sample_players}


class TestLoadPlayers:
    def test_raises_on_an_empty_database(self, player_db, tmp_path):
        empty = tmp_path / "empty.json"
        empty.write_text(json.dumps({"players": []}), encoding="utf-8")
        player_db.PLAYER_DATABASE_PATH = empty

        with pytest.raises(RuntimeError, match="empty"):
            player_db.randomPlayer()
