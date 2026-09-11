"""Rating a career, and deciding whether it belongs in the pool at all.

The judgements here are opinions about what makes a good puzzle, so the tests
pin the shape of those opinions -- that obscurity outweighs path length, that a
star is never rated hard, that the daily stays recognisable.
"""

import json
from pathlib import Path

import difficulty as D
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


class TestPools:
    """Choosing a pool is choosing how famous the players are, and nothing else.

    The distinction that matters: `difficulty_for` folds fame together with path
    length, so selecting on it would drop a famous player with seven clubs --
    which is the best puzzle this game has, not the worst.
    """

    def test_pools_are_cumulative(self):
        # Loosening the setting must only ever add players. Somebody who widens
        # the pool and stops seeing names they had before would reasonably call
        # that a bug.
        ceilings = [
            D.max_fame(D.POOL_BIG_NAMES),
            D.max_fame(D.POOL_MIXED),
            D.max_fame(D.POOL_DEEP_CUTS),
        ]
        assert ceilings == sorted(ceilings)

    def test_a_star_is_in_every_pool(self):
        star = D.fame_for(24.0, 1100, 8)
        assert all(D.in_pool(star, name) for name in D.POOLS)

    def test_an_unknown_is_only_in_the_widest_pool(self):
        unknown = D.fame_for(5.2, 166, 0)
        assert D.in_pool(unknown, D.POOL_DEEP_CUTS)
        assert not D.in_pool(unknown, D.POOL_MIXED)
        assert not D.in_pool(unknown, D.POOL_BIG_NAMES)

    def test_a_famous_player_with_a_long_path_stays_in_the_narrow_pool(self):
        # The whole reason selection is on fame rather than difficulty: a
        # one-time All-Star who played for eight clubs rates a 3 on the
        # composite, so a difficulty<=2 filter would drop him -- and he is
        # precisely the puzzle this game is for.
        assert D.difficulty_for(14.0, 8, 700, 1) == 3
        assert D.in_pool(D.fame_for(14.0, 700, 1), D.POOL_BIG_NAMES)

    def test_an_unknown_pool_name_falls_back_rather_than_raising(self):
        # It arrives from a request body. A stale client should get a game.
        assert D.max_fame("nonsense") == D.POOLS[D.DEFAULT_POOL]

    def test_every_pool_has_a_label_and_a_note(self):
        choices = D.pool_choices()
        assert {c["id"] for c in choices} == set(D.POOLS)
        assert all(c["label"] and c["note"] for c in choices)

    def test_missing_fame_is_not_silently_included(self):
        # A player the pool could not rate is excluded rather than treated as a
        # star, which is the direction that cannot disappoint anybody.
        assert not D.in_pool(None, D.POOL_BIG_NAMES)


class TestLongevityIsNotFame:
    """Games played is evidence of recognisability, not a substitute for it.

    Terry Dehere averaged exactly 8.0 points over exactly 402 games with no
    All-Star selection. Both thresholds were set at those numbers, he cleared
    both by a hair, and the longevity rescue carried him into the most
    recognisable tier -- alongside Mitch Richmond and Kevin Love.
    """

    def test_five_seasons_of_a_role_player_is_not_a_big_name(self):
        fame = D.fame_for(8.0, 402, 0)
        assert not D.in_pool(fame, D.POOL_BIG_NAMES)
        assert D.in_pool(fame, D.POOL_MIXED)

    def test_a_long_career_still_rescues_a_low_scorer(self):
        # The rule longevity exists for. Robert Horry averaged 7.0 over 1,107
        # games with no All-Star selection and is not obscure to anybody.
        assert D.in_pool(D.fame_for(7.0, 1107, 0), D.POOL_BIG_NAMES)
        assert D.in_pool(D.fame_for(8.3, 1287, 0), D.POOL_BIG_NAMES)  # Derek Fisher

    def test_an_all_star_is_never_demoted_by_this(self):
        # Rodman: 7.3 over 911 games, two selections. Scoring calls him
        # obscure; anyone who watched basketball in the nineties does not.
        assert D.fame_for(7.3, 911, 2) == 0

    def test_the_promotion_rule_did_not_move_with_it(self):
        # Forty-five careers sit between the two thresholds and are promoted
        # only by the longevity rescue. Retuning what "well known" means must
        # not quietly drop them out of the playable pool.
        assert D.PROMOTION_CAREER_GAMES < D.SOLID_CAREER_GAMES
        assert D.should_promote(4.6, 3, "ok", 456)  # Brian Cardinal
        assert D.should_promote(3.1, 4, "ok", 520)  # Brian Scalabrine


class TestRate:
    """One derivation, used everywhere a pool is built."""

    def test_it_ignores_a_stored_difficulty(self):
        # players.difficulty is written at import, so it is a snapshot of the
        # rules on the day that import ran. Reading it makes every retune
        # silently stale, because a stale tier is still a valid tier.
        row = {
            "ppg": 8.0,
            "games": 402,
            "all_star_selections": 0,
            "teams": ["a", "b"],
            "difficulty": 1,
        }
        fame, tier = D.rate(row)
        assert (fame, tier) == (2, 3)

    def test_it_reads_either_column_naming(self):
        # The database calls them career_ppg/career_games; the pool file calls
        # them ppg/games. Both reach this.
        from_db = D.rate(
            {"career_ppg": 8.0, "career_games": 402, "stints": [{"team": "a"}, {"team": "b"}]}
        )
        from_file = D.rate({"ppg": 8.0, "games": 402, "teams": ["a", "b"]})
        assert from_db == from_file


class TestShortAndOldCareers:
    """Two ways a good scoring average overstated how known somebody is.

    Fourteen per cent of Big names got there on scoring alone with no career
    length behind it, and the longevity rescue promoted players nobody has
    watched in forty years into the same tier as Kevin Durant.
    """

    def test_a_good_average_over_two_seasons_is_not_a_big_name(self):
        """Walter Berry's shape: 14.1 a game over 205 games, no All-Star.

        Dated to 2015 on purpose -- after the era cutoff and before the still-
        recent one -- so the only rule that can exclude him is the career-length
        floor. The first version of this test used Berry's real 1989 and passed
        on the era nudge alone, which meant the floor itself was untested and a
        mutation check caught it.
        """
        fame = D.fame_for(14.1, 205, 0, last_season=2015)
        assert not D.in_pool(fame, D.POOL_BIG_NAMES)
        assert D.in_pool(fame, D.POOL_MIXED)

    def test_the_real_walter_berry_is_excluded_twice_over(self):
        # Short and long gone: both rules apply, and they stack.
        assert D.fame_for(14.1, 205, 0, last_season=1989) == 3

    def test_a_short_career_that_is_still_going_is_not_penalised(self):
        # Jaden Ivey has played no longer than Walter Berry and is perfectly
        # recognisable, because he is playing now. Being current is its own
        # kind of fame and the only kind this data can see directly.
        fame = D.fame_for(14.8, 218, 0, last_season=2026)
        assert D.in_pool(fame, D.POOL_BIG_NAMES)

    def test_a_long_career_from_a_distant_era_is_nudged_down(self):
        # Billy Paultz: 8.5 a game, 637 games, last seen in 1985. The longevity
        # rescue had him level with Kevin Durant.
        assert not D.in_pool(D.fame_for(8.5, 637, 0, last_season=1985), D.POOL_BIG_NAMES)
        assert D.in_pool(D.fame_for(8.5, 637, 0, last_season=1985), D.POOL_MIXED)

    def test_the_same_career_today_is_not_nudged(self):
        assert D.in_pool(D.fame_for(8.5, 637, 0, last_season=2024), D.POOL_BIG_NAMES)

    def test_an_all_star_is_exempt_from_the_era_nudge(self):
        # Direct evidence people knew the name at the time, which is exactly
        # what the nudge is guessing at in its absence.
        assert D.fame_for(7.3, 911, 2, last_season=1985) == 0
        assert D.fame_for(10.0, 500, 1, last_season=1975) == 1

    def test_an_unknown_season_is_not_treated_as_old(self):
        # Absent is not ancient. Penalising it would quietly demote every
        # career the source could not date.
        assert D.fame_for(12.0, 700, 0, last_season=None) == D.fame_for(12.0, 700, 0)

    def test_the_era_nudge_stacks_with_longevity_rather_than_replacing_it(self):
        # A long old career should still beat a short old one.
        long_ago = D.fame_for(12.0, 900, 0, last_season=1985)
        brief_ago = D.fame_for(12.0, 200, 0, last_season=1985)
        assert long_ago < brief_ago


class TestLongevityCannotMakeAStar:
    """Tier 0 is where Durant and Rodman sit, and games played is not a ticket.

    The -2 for a long career could carry anybody there. Caldwell Jones reached
    the most recognisable tier on 6.2 points a game, and Dave Greenwood on 10.2
    -- both purely for having turned out eight hundred times.
    """

    def test_a_long_quiet_career_is_recognisable_but_not_a_star(self):
        """Dave Greenwood's shape: 10.2 a game over 823 games, no All-Star.

        Dated modern so the era nudge is out of the way and the cap is the only
        thing under test. Without it this scores 2 and the -2 for a long career
        takes it to 0 -- the tier Durant and Rodman are in.

        The first version of this test used Caldwell Jones at 6.2 a game, which
        lands on 1 with or without the cap, so it asserted nothing. The mutation
        check caught that.
        """
        assert D.fame_for(10.2, 823, 0, last_season=2010) == 1

    def test_even_a_thousand_quiet_games_stays_out_of_the_top_tier(self):
        # Caldwell Jones: 6.2 a game over 1,068 games.
        assert D.fame_for(6.2, 1068, 0, last_season=2010) >= 1

    def test_star_level_scoring_still_reaches_the_top_tier(self):
        # The cap needs direct evidence, and a scoring average nobody achieves
        # quietly is evidence.
        assert D.fame_for(24.6, 1000, 0, last_season=2010) == 0

    def test_all_star_selections_bypass_the_cap(self):
        assert D.fame_for(7.3, 911, 2, last_season=2000) == 0

    def test_an_early_nineties_career_is_not_treated_as_recent(self):
        # The two that were reported. The cutoff was 1990, which both slipped
        # past -- and to somebody playing today the early nineties is not
        # meaningfully nearer than the eighties.
        greenwood = D.fame_for(10.2, 823, 0, last_season=1991)
        higgins = D.fame_for(9.0, 779, 0, last_season=1995)
        assert not D.in_pool(greenwood, D.POOL_BIG_NAMES)
        assert not D.in_pool(higgins, D.POOL_BIG_NAMES)
        assert D.in_pool(greenwood, D.POOL_MIXED)
        assert D.in_pool(higgins, D.POOL_MIXED)

    def test_the_greats_of_that_era_survive_on_their_selections(self):
        # Kareem, Gervin, Frazier: exempt because an All-Star selection is
        # direct evidence, which is what everything else here approximates.
        assert D.in_pool(D.fame_for(24.6, 1560, 17, last_season=1989), D.POOL_BIG_NAMES)
        assert D.in_pool(D.fame_for(18.9, 825, 7, last_season=1980), D.POOL_BIG_NAMES)

    def test_a_modern_long_career_is_unaffected(self):
        # Horry, Fisher, Bowen, Battier: none an All-Star, none obscure.
        for ppg, games in ((7.0, 1107), (8.3, 1287), (6.1, 873), (8.6, 977)):
            assert D.in_pool(D.fame_for(ppg, games, 0, last_season=2010), D.POOL_BIG_NAMES)
