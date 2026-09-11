"""Scheduling the daily puzzle.

`plan` is pure, so the rules that matter -- no repeats, never overwrite an
existing row, fail loudly rather than repeat -- are tested without a database.
"""

import random
from datetime import date, timedelta

import pytest
from difficulty import DAILY_MAX_FAME, daily_fit, daily_target
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


class TestWeeklyCurve:
    """Filling a calendar to a difficulty curve rather than a flat preference.

    `prefer` could only sort the pool once, which cannot express "Monday and
    Saturday want different players". `fit` grades each player against each
    date, so the calendar has a shape.
    """

    @staticmethod
    def _pool(n=400):
        # Spread across every tier and both sides of the fame floor, so the
        # scheduler has real choices and real temptations.
        pool = []
        for i in range(n):
            tier = (i % 5) + 1
            pool.append(
                {
                    "id": i,
                    "name": f"Player {i}",
                    "teams": ["a", "b"],
                    "difficulty": tier,
                    # Mirrors the real pool's shape: the hardest tier is never
                    # within the fame floor.
                    "fame": 0 if tier <= 2 else 2 if tier <= 4 else 4,
                }
            )
        return pool

    def test_each_weekday_lands_on_its_target(self):
        chosen = plan(self._pool(), date(2026, 10, 5), 28, fit=daily_fit, rng=random.Random(1))
        assert len(chosen) == 28
        for day, player in chosen:
            assert player["difficulty"] == daily_target(day), day.strftime("%a")

    def test_the_week_actually_ramps(self):
        # The point of the feature, stated as a property rather than by
        # restating the table: Monday must not be harder than Saturday.
        chosen = plan(self._pool(), date(2026, 10, 5), 70, fit=daily_fit, rng=random.Random(2))
        by_day = {}
        for day, player in chosen:
            by_day.setdefault(day.weekday(), []).append(player["difficulty"])
        mondays = sum(by_day[0]) / len(by_day[0])
        saturdays = sum(by_day[5]) / len(by_day[5])
        assert mondays < saturdays

    def test_an_unrecognisable_player_is_never_scheduled_while_anyone_else_is_free(self):
        """The complaint the fame floor answers.

        Deliberately built so the floor is the only thing standing between the
        calendar and an unknown player: there are no tier-4 players at all, so
        Saturday's target of 4 is equidistant from tier 3 (fame 2, fine) and
        tier 5 (fame 4, a lookup). Without the floor those tie and recency
        decides, which puts unknowns on the front page about half the time.

        The first version of this test used a pool with plenty of tier 4 in it,
        so the fallback never happened and the test passed with the floor
        deleted. It is the repo's recurring bug shape, in a test.
        """
        pool = []
        for i in range(200):
            tier = 3 if i % 2 == 0 else 5
            pool.append(
                {
                    "id": i,
                    "name": f"Player {i}",
                    "teams": ["a", "b"],
                    "difficulty": tier,
                    "fame": 2 if tier == 3 else 4,
                }
            )
        chosen = plan(pool, date(2026, 10, 5), 60, fit=daily_fit, rng=random.Random(3))
        assert len(chosen) == 60
        assert all(player["fame"] <= DAILY_MAX_FAME for _, player in chosen)

    def test_nobody_is_scheduled_twice(self):
        chosen = plan(self._pool(), date(2026, 10, 5), 90, fit=daily_fit, rng=random.Random(4))
        ids = [player["id"] for _, player in chosen]
        assert len(ids) == len(set(ids))

    def test_an_existing_puzzle_is_never_overwritten(self):
        # A scheduled puzzle is a promise, curve or no curve.
        start = date(2026, 10, 5)
        fixed = {"2026-10-07": {"player_id": 999, "payload": {}}}
        chosen = plan(self._pool(), start, 10, already_scheduled=fixed, fit=daily_fit)
        assert date(2026, 10, 7) not in [day for day, _ in chosen]

    def test_the_floor_widens_rather_than_failing(self):
        # Ten days, and only four players who clear the fame floor. An empty
        # day is a broken game; a slightly-off day is only slightly off.
        thin = [
            {"id": i, "name": f"P{i}", "teams": ["a"], "difficulty": 2, "fame": 0 if i < 4 else 4}
            for i in range(10)
        ]
        chosen = plan(thin, date(2026, 10, 5), 10, fit=daily_fit)
        assert len(chosen) == 10

    def test_an_unrated_player_is_treated_as_unfit_rather_than_as_a_star(self):
        pool = [
            {"id": 1, "name": "Rated", "teams": ["a"], "difficulty": 1, "fame": 0},
            {"id": 2, "name": "Unrated", "teams": ["a"], "difficulty": None, "fame": None},
        ]
        chosen = plan(pool, date(2026, 10, 5), 1, fit=daily_fit)  # a Monday
        assert chosen[0][1]["name"] == "Rated"

    def test_a_modern_career_is_preferred_within_a_tier(self):
        # Fame is measured from scoring, longevity and All-Star selections, all
        # of which a 1960s journeyman can clear while being unplaceable today.
        pool = [
            {
                "id": 1,
                "name": "Old",
                "teams": ["a"],
                "difficulty": 1,
                "fame": 0,
                "last_season": 1974,
            },
            {
                "id": 2,
                "name": "New",
                "teams": ["a"],
                "difficulty": 1,
                "fame": 0,
                "last_season": 2019,
            },
        ]
        chosen = plan(pool, date(2026, 10, 5), 1, fit=daily_fit)  # a Monday
        assert chosen[0][1]["name"] == "New"

    def test_the_era_tilt_does_not_outrank_the_tier(self):
        # Weighted below a tier mismatch on purpose. Getting the day's
        # difficulty right matters more than the decade, and a calendar that
        # began in 1990 would be a worse game as well as a less accurate one.
        pool = [
            {
                "id": 1,
                "name": "Old exact",
                "teams": ["a"],
                "difficulty": 1,
                "fame": 0,
                "last_season": 1974,
            },
            {
                "id": 2,
                "name": "New wrong",
                "teams": ["a"],
                "difficulty": 3,
                "fame": 0,
                "last_season": 2019,
            },
        ]
        chosen = plan(pool, date(2026, 10, 5), 1, fit=daily_fit)  # Monday targets 1
        assert chosen[0][1]["name"] == "Old exact"

    def test_an_undated_career_is_not_penalised(self):
        # Absent is not old. Treating it as old would quietly demote every
        # player the source could not date.
        pool = [
            {"id": 1, "name": "Undated", "teams": ["a"], "difficulty": 1, "fame": 0},
            {
                "id": 2,
                "name": "Old",
                "teams": ["a"],
                "difficulty": 1,
                "fame": 0,
                "last_season": 1974,
            },
        ]
        chosen = plan(pool, date(2026, 10, 5), 1, fit=daily_fit)
        assert chosen[0][1]["name"] == "Undated"

    def test_recency_breaks_ties_within_a_tier(self):
        # Two equally good fits for Monday; the one used longer ago wins.
        pool = [
            {"id": 1, "name": "Recent", "teams": ["a"], "difficulty": 1, "fame": 0},
            {"id": 2, "name": "Ancient", "teams": ["a"], "difficulty": 1, "fame": 0},
        ]
        chosen = plan(
            pool,
            date(2026, 10, 5),
            1,
            last_used={1: "2026-10-01", 2: "2025-01-01"},
            fit=daily_fit,
        )
        assert chosen[0][1]["name"] == "Ancient"
