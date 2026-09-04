"""Career validation.

The point of these checks is that they run over thousands of careers with no
source to compare against, so what matters is that "reject" really means
provably wrong -- a false rejection silently shrinks the puzzle pool and nobody
notices.
"""

import json
from pathlib import Path

import pytest
from validation import (
    format_report,
    implausible_problems,
    impossible_problems,
    validate,
    validate_pool,
)

POOL = Path(__file__).parents[1] / "nba_players.json"
GOOD = ["boston celtics", "miami heat", "utah jazz"]


class TestImpossible:
    """Provably wrong. These must never fire on a real career."""

    def test_a_clean_career_has_no_problems(self):
        assert impossible_problems(GOOD) == []

    @pytest.mark.parametrize(
        "teams",
        [
            ["oklahoma city thunder", "seattle supersonics"],
            ["memphis grizzlies", "vancouver grizzlies"],
            ["brooklyn nets", "new jersey nets"],
            ["washington wizards", "washington bullets"],
            ["new orleans pelicans", "new orleans hornets"],
        ],
        ids=["sea", "van", "nj", "bullets", "noh"],
    )
    def test_a_franchise_cannot_precede_its_own_earlier_name(self, teams):
        assert impossible_problems(teams)

    @pytest.mark.parametrize(
        "teams",
        [
            ["seattle supersonics", "oklahoma city thunder"],
            ["vancouver grizzlies", "memphis grizzlies"],
            ["new jersey nets", "brooklyn nets"],
        ],
        ids=["sea", "van", "nj"],
    )
    def test_the_right_order_is_accepted(self, teams):
        assert impossible_problems(teams) == []

    def test_a_franchise_alone_is_fine_either_way(self):
        """Most players saw only one of the two names."""
        assert impossible_problems(["oklahoma city thunder", "miami heat"]) == []
        assert impossible_problems(["seattle supersonics", "miami heat"]) == []

    def test_consecutive_duplicates_are_a_failed_collapse(self):
        assert impossible_problems(["miami heat", "miami heat"])

    def test_a_genuine_return_is_not_a_duplicate(self):
        """Cleveland to Miami and back is the shape the game is built on."""
        assert (
            impossible_problems(["cleveland cavaliers", "miami heat", "cleveland cavaliers"]) == []
        )

    def test_an_empty_career_is_rejected(self):
        assert impossible_problems([])


class TestImplausible:
    def test_a_normal_career_is_not_flagged(self):
        assert implausible_problems(GOOD) == []

    def test_alternation_is_flagged(self):
        """The pre-1985 ordering bug: Bob Lanier as DET/MIL/DET/MIL."""
        problems = implausible_problems(
            ["detroit pistons", "milwaukee bucks", "detroit pistons", "milwaukee bucks"]
        )
        assert any("alternation" in p for p in problems)

    def test_a_single_return_is_not_alternation(self):
        assert implausible_problems(["phoenix suns", "boston celtics", "phoenix suns"]) == []

    def test_a_very_long_career_is_flagged_not_rejected(self):
        teams = [f"team {i}" for i in range(13)]
        assert validate(teams)["verdict"] == "review"

    def test_a_one_team_career_is_flagged_as_unusable(self):
        problems = implausible_problems(["boston celtics"])
        assert any("two distinct" in p for p in problems)


class TestVerdicts:
    def test_ok(self):
        assert validate(GOOD)["verdict"] == "ok"

    def test_review(self):
        teams = ["detroit pistons", "milwaukee bucks", "detroit pistons", "milwaukee bucks"]
        assert validate(teams)["verdict"] == "review"

    def test_reject(self):
        assert validate(["oklahoma city thunder", "seattle supersonics"])["verdict"] == "reject"

    def test_impossible_outranks_implausible(self):
        """Something provably wrong is never merely queued for review."""
        teams = ["brooklyn nets", "new jersey nets", "brooklyn nets", "new jersey nets"]
        result = validate(teams)
        assert result["verdict"] == "reject"
        assert result["implausible"], "the implausible signal is still reported"


class TestAgainstTheRealPool:
    """These run over backend/nba_players.json, the data actually in the game."""

    @pytest.fixture(scope="class")
    def summary(self):
        with open(POOL, encoding="utf-8") as f:
            return validate_pool(json.load(f)["players"])

    def test_nothing_in_the_shipped_pool_is_provably_wrong(self, summary):
        assert summary["reject"] == [], format_report(summary)

    def test_the_review_queue_stays_small_enough_to_be_read(self, summary):
        """The whole approach fails if it flags everything."""
        assert len(summary["review"]) / summary["total"] < 0.10, format_report(summary)

    def test_it_still_catches_the_known_pre_1985_ordering_bug(self, summary):
        """Bob Lanier, Connie Hawkins and Dwight Jones, found with no source.

        If this stops failing, either the pool was fixed -- in which case delete
        this test -- or the check stopped working.
        """
        flagged = {entry["name"] for entry in summary["review"]}
        assert {"Bob Lanier", "Connie Hawkins", "Dwight Jones"} <= flagged


class TestReport:
    def test_it_states_the_review_rate(self):
        report = format_report(validate_pool([{"name": "A", "teams": GOOD}]))
        assert "review rate" in report

    def test_it_names_the_reason_not_just_the_player(self):
        pool = [{"name": "Impossible Guy", "teams": ["brooklyn nets", "new jersey nets"]}]
        report = format_report(validate_pool(pool))
        assert "Impossible Guy" in report
        assert "same franchise" in report
