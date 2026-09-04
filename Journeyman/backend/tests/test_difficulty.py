"""Rating a career, and deciding whether it belongs in the pool at all.

The judgements here are opinions about what makes a good puzzle, so the tests
pin the shape of those opinions -- that obscurity outweighs path length, that a
star is never rated hard, that the daily stays recognisable.
"""

import json
from pathlib import Path

import pytest
from difficulty import (
    MAX_DAILY_DIFFICULTY,
    MIN_PROMOTABLE_PPG,
    describe,
    difficulty_for,
    is_daily_eligible,
    should_promote,
)

POOL = Path(__file__).parents[1] / "nba_players.json"


class TestDifficulty:
    def test_a_star_with_a_short_path_is_the_easiest(self):
        assert difficulty_for(29.2, 2) == 1  # Luka Doncic

    def test_an_obscure_player_with_a_long_path_is_the_hardest(self):
        assert difficulty_for(5.8, 13) == 5  # Garrett Temple

    def test_a_star_is_never_rated_hard_however_long_the_path(self):
        """Knowing the player is most of the puzzle."""
        assert difficulty_for(25.0, 12) <= 3

    def test_obscurity_outweighs_path_length(self):
        """A name you cannot place cannot be reasoned out; a long path can."""
        obscure_short = difficulty_for(5.0, 2)
        known_long = difficulty_for(20.0, 9)
        assert obscure_short > known_long

    def test_a_longer_path_is_never_easier(self):
        for ppg in (5.0, 9.0, 14.0, 22.0):
            ratings = [difficulty_for(ppg, n) for n in (2, 4, 6, 9)]
            assert ratings == sorted(ratings), (ppg, ratings)

    def test_a_more_obscure_player_is_never_easier(self):
        for stints in (2, 5, 9):
            ratings = [difficulty_for(ppg, stints) for ppg in (25.0, 14.0, 9.0, 5.0)]
            assert ratings == sorted(ratings), (stints, ratings)

    def test_it_always_lands_in_range(self):
        for ppg in (0.0, 5.0, 12.0, 30.0, 100.0):
            for stints in (1, 2, 8, 20):
                assert 1 <= difficulty_for(ppg, stints) <= 5

    def test_missing_ppg_is_treated_as_obscure(self):
        """A source with no scoring data must not silently rate everyone easy."""
        assert difficulty_for(None, 3) >= 4

    def test_every_tier_has_a_description(self):
        for tier in range(1, 6):
            assert describe(tier) != "unrated"


class TestDailyEligibility:
    def test_the_easy_tiers_are_eligible(self):
        assert all(is_daily_eligible(t) for t in range(1, MAX_DAILY_DIFFICULTY + 1))

    def test_the_hard_tiers_are_not(self):
        assert not any(is_daily_eligible(t) for t in range(MAX_DAILY_DIFFICULTY + 1, 6))

    def test_an_unrated_player_is_not_eligible(self):
        """Absent a rating, keep it out of the shop window."""
        assert not is_daily_eligible(None)

    def test_the_ceiling_leaves_room_for_a_real_puzzle(self):
        assert 2 <= MAX_DAILY_DIFFICULTY <= 4


class TestPromotion:
    def test_a_clean_ordinary_career_is_promoted(self):
        assert should_promote(9.0, 4, "ok")

    @pytest.mark.parametrize("status", ["review", "reject", "unreviewed"])
    def test_anything_validation_did_not_clear_is_held_back(self, status):
        assert not should_promote(9.0, 4, status)

    def test_a_career_below_the_floor_is_held_back(self):
        assert not should_promote(MIN_PROMOTABLE_PPG - 0.1, 4, "ok")

    def test_a_single_team_career_is_held_back(self):
        """The game is about a path. One stop is not one."""
        assert not should_promote(20.0, 1, "ok")

    def test_an_unguessably_long_career_is_held_back(self):
        assert not should_promote(9.0, 20, "ok")

    def test_missing_ppg_is_held_back_rather_than_assumed_good(self):
        assert not should_promote(None, 4, "ok")


class TestAgainstTheShippedPool:
    @pytest.fixture(scope="class")
    def players(self):
        with open(POOL, encoding="utf-8") as f:
            return json.load(f)["players"]

    def test_most_of_the_pool_is_promotable(self, players):
        promotable = [p for p in players if should_promote(p["ppg"], len(set(p["teams"])), "ok")]
        assert len(promotable) / len(players) > 0.9

    def test_the_daily_eligible_share_is_recorded(self, players):
        """The pool's real constraint, pinned so a change is noticed.

        Only about a third of the shipped pool is recognisable enough for a
        daily -- roughly 73 careers, which cannot fill a quarter without
        repeating. That is why the scheduler widens rather than filters, and it
        is the strongest argument for growing the pool.
        """
        eligible = [
            p for p in players if is_daily_eligible(difficulty_for(p["ppg"], len(p["teams"])))
        ]
        assert 50 <= len(eligible) <= 120, len(eligible)

    def test_every_tier_is_represented(self, players):
        tiers = {difficulty_for(p["ppg"], len(p["teams"])) for p in players}
        assert tiers == {1, 2, 3, 4, 5}
