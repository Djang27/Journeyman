"""Scheduling the daily puzzle.

`plan` is pure, so the rules that matter -- no repeats, never overwrite an
existing row, fail loudly rather than repeat -- are tested without a database.
"""

from datetime import date, timedelta

import pytest
from puzzles_repo import REPEAT_WINDOW_DAYS, NotEnoughPlayers, payload_for, plan

START = date(2026, 9, 4)


def pool(n, first_id=1):
    return [
        {"id": first_id + i, "name": f"Player {first_id + i}", "teams": ["miami heat", "utah jazz"]}
        for i in range(n)
    ]


class TestPayload:
    def test_carries_what_a_session_needs(self):
        assert payload_for(pool(1)[0]) == {
            "player_id": 1,
            "player_name": "Player 1",
            "teams": ["miami heat", "utah jazz"],
        }

    def test_the_teams_are_copied_not_referenced(self):
        """A puzzle already scheduled must not change if the player record does."""
        player = pool(1)[0]
        payload = payload_for(player)
        player["teams"].append("boston celtics")
        assert payload["teams"] == ["miami heat", "utah jazz"]


class TestPlan:
    def test_fills_every_day_in_the_window(self):
        assert len(plan(pool(30), START, 7)) == 7

    def test_never_repeats_a_player_within_the_window(self):
        chosen = plan(pool(30), START, 20)
        ids = [player["id"] for _, player in chosen]
        assert len(ids) == len(set(ids))

    def test_dates_are_consecutive_from_the_start(self):
        chosen = plan(pool(10), START, 5)
        assert [d for d, _ in chosen] == [START + timedelta(days=i) for i in range(5)]

    def test_an_already_scheduled_date_is_left_alone(self):
        """A scheduled puzzle is a promise. Overwriting it is what this replaces."""
        existing = {str(START + timedelta(days=2)): {"player_id": 99}}
        chosen = plan(pool(10), START, 5, already_scheduled=existing)

        assert len(chosen) == 4
        assert str(START + timedelta(days=2)) not in {str(d) for d, _ in chosen}

    def test_a_player_already_on_the_calendar_is_not_reused(self):
        existing = {str(START + timedelta(days=1)): {"player_id": 3}}
        chosen = plan(pool(10), START, 5, already_scheduled=existing)
        assert 3 not in {player["id"] for _, player in chosen}

    def test_recently_used_players_are_avoided_when_the_pool_allows(self):
        recent = {
            1: "2026-09-01",
            2: "2026-09-02",
            3: "2026-09-03",
            4: "2026-09-01",
            5: "2026-09-02",
        }
        chosen = plan(pool(10), START, 5, last_used=recent)
        assert not ({p["id"] for _, p in chosen} & set(recent))

    def test_the_least_recently_used_are_preferred(self):
        """Once everyone has been used, the oldest come back first."""
        recent = {i: f"2026-0{i}-01" for i in range(1, 6)}
        chosen = plan(pool(5), START, 2, last_used=recent)
        assert [p["id"] for _, p in chosen] == [1, 2]

    def test_it_still_schedules_when_everyone_was_used_recently(self):
        """Hard exclusion could not do this, and the arithmetic requires it.

        With 193 promoted players, filling 90 days while excluding 180 days of
        history needs 270 distinct players. Ranking never runs out.
        """
        recent = {i: "2026-09-01" for i in range(1, 11)}
        assert len(plan(pool(10), START, 10, last_used=recent)) == 10

    def test_it_refuses_only_when_the_pool_cannot_cover_the_horizon(self):
        with pytest.raises(NotEnoughPlayers, match="days to fill"):
            plan(pool(3), START, 10)

    def test_the_error_says_how_to_fix_it(self):
        with pytest.raises(NotEnoughPlayers, match="Promote more players"):
            plan(pool(3), START, 10)

    def test_the_lookback_window_is_wide_enough_to_matter(self):
        assert REPEAT_WINDOW_DAYS >= 180

    def test_it_is_deterministic_for_a_given_seed(self):
        """So a dry run shows what the real run will do."""
        import random

        first = plan(pool(30), START, 7, rng=random.Random(1))
        second = plan(pool(30), START, 7, rng=random.Random(1))
        assert [p["id"] for _, p in first] == [p["id"] for _, p in second]

    def test_a_fully_scheduled_window_is_a_no_op(self):
        existing = {str(START + timedelta(days=i)): {"player_id": i + 1} for i in range(5)}
        assert plan(pool(10), START, 5, already_scheduled=existing) == []
