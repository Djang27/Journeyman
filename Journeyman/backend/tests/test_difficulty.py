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

    def test_most_unambiguous_careers_are_promotable(self, players):
        usable = [p for p in players if not p.get("ambiguous_seasons")]
        promotable = [
            p
            for p in usable
            if should_promote(p["ppg"], len(set(p["teams"])), "ok", p.get("games"))
        ]
        assert len(promotable) / len(usable) > 0.6

    def test_there_are_enough_daily_eligible_careers_for_years_of_dailies(self, players):
        """The constraint that drove the source change, now measured the other way.

        The old 200-player pool held about 70 careers recognisable enough for a
        daily -- ten weeks before repeating. Anything under a year here means
        the pool has regressed.
        """
        eligible = [
            p
            for p in players
            if not p.get("ambiguous_seasons")
            and is_daily_eligible(
                difficulty_for(
                    p["ppg"], len(p["teams"]), p.get("games"), p.get("all_star_selections", 0)
                )
            )
        ]
        assert len(eligible) > 365, len(eligible)

    def test_every_tier_is_represented(self, players):
        tiers = {
            difficulty_for(
                p["ppg"], len(p["teams"]), p.get("games"), p.get("all_star_selections", 0)
            )
            for p in players
        }
        assert tiers == {1, 2, 3, 4, 5}

    def test_a_famous_low_scorer_is_not_rated_obscure(self, players):
        """Dennis Rodman: 7.3 a game, 911 games, two All-Star selections.

        Scoring average alone calls him obscure. He is the reason the model
        takes longevity and All-Star selections as well.
        """
        rodman = next((p for p in players if p["name"] == "Dennis Rodman"), None)
        assert rodman is not None
        tier = difficulty_for(
            rodman["ppg"], len(rodman["teams"]), rodman["games"], rodman["all_star_selections"]
        )
        assert tier <= 2, tier
