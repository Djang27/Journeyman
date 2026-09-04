"""Building a career from season rows.

The cases that matter are the ones that produced Bob Lanier as DET/MIL/DET/MIL:
a mid-season trade whose two rows arrive in the wrong order. These reproduce
that shape directly rather than through the live API.
"""

import pytest
from career_builder import (
    build_stints,
    group_by_season,
    order_within_season,
    season_start_year,
    teams_of,
)

ABBR = {
    "DET": "detroit pistons",
    "MIL": "milwaukee bucks",
    "PHX": "phoenix suns",
    "LAL": "los angeles lakers",
    "ATL": "atlanta hawks",
    "CLE": "cleveland cavaliers",
    "MIA": "miami heat",
}


def team_of(row):
    return ABBR.get(row.get("TEAM_ABBREVIATION"))


def row(season, abbr):
    return {"SEASON_ID": season, "TEAM_ABBREVIATION": abbr}


class TestSeasonStartYear:
    @pytest.mark.parametrize(
        "value,expected", [("1979-80", 1979), ("22015", 2015), ("2015-16", 2015)]
    )
    def test_parses_the_formats_the_api_uses(self, value, expected):
        assert season_start_year(value) == expected

    @pytest.mark.parametrize("value", [None, "", "not-a-season", "0001"])
    def test_rejects_what_it_cannot_read(self, value):
        assert season_start_year(value) is None


class TestGroupBySeason:
    def test_groups_rows_by_year(self):
        rows = [row("1979-80", "DET"), row("1980-81", "MIL")]
        assert group_by_season(rows, team_of) == {
            1979: ["detroit pistons"],
            1980: ["milwaukee bucks"],
        }

    def test_the_combined_row_is_dropped(self):
        """TOT is the NBA's own total for a split season, not a team."""
        rows = [row("1979-80", "TOT"), row("1979-80", "DET"), row("1979-80", "MIL")]
        assert group_by_season(rows, team_of)[1979] == ["detroit pistons", "milwaukee bucks"]

    def test_unknown_teams_are_dropped(self):
        assert group_by_season([row("1979-80", "XXX")], team_of) == {}

    def test_a_team_appearing_twice_in_a_season_is_recorded_once(self):
        rows = [row("1979-80", "DET"), row("1979-80", "DET")]
        assert group_by_season(rows, team_of)[1979] == ["detroit pistons"]


class TestOrderWithinSeason:
    def test_a_single_team_needs_no_ordering(self):
        assert order_within_season(["a"], [], []) == (["a"], False)

    def test_the_team_from_last_season_comes_first(self):
        ordered, ambiguous = order_within_season(["b", "a"], previous=["a"], following=[])
        assert ordered == ["a", "b"]
        assert not ambiguous

    def test_the_team_continuing_next_season_comes_last(self):
        ordered, ambiguous = order_within_season(["b", "a"], previous=[], following=["b"])
        assert ordered == ["a", "b"]
        assert not ambiguous

    def test_both_neighbours_agreeing_is_unambiguous(self):
        ordered, ambiguous = order_within_season(["b", "a"], previous=["a"], following=["b"])
        assert ordered == ["a", "b"]
        assert not ambiguous

    def test_no_neighbour_evidence_is_reported_as_ambiguous(self):
        """A one-season career split across two teams cannot be ordered."""
        ordered, ambiguous = order_within_season(["a", "b"], previous=[], following=[])
        assert ambiguous


class TestBuildStints:
    def test_a_simple_career(self):
        rows = [row("2010-11", "MIA"), row("2011-12", "MIA"), row("2012-13", "CLE")]
        stints, _ = build_stints(rows, team_of)
        assert teams_of(stints) == ["miami heat", "cleveland cavaliers"]

    def test_seasons_are_recorded_per_stint(self):
        rows = [row("2010-11", "MIA"), row("2011-12", "MIA"), row("2012-13", "CLE")]
        stints, _ = build_stints(rows, team_of)
        assert stints[0] == {"team": "miami heat", "from_season": 2010, "to_season": 2011}
        assert stints[1] == {"team": "cleveland cavaliers", "from_season": 2012, "to_season": 2012}

    def test_rows_out_of_order_are_sorted(self):
        rows = [row("2012-13", "CLE"), row("2010-11", "MIA")]
        stints, _ = build_stints(rows, team_of)
        assert teams_of(stints) == ["miami heat", "cleveland cavaliers"]

    def test_bob_lanier(self):
        """The bug, reproduced: a traded season whose rows arrive reversed.

        Detroit 1970-79, traded to Milwaukee during 1979-80, Milwaukee after.
        The old code produced DET / MIL / DET / MIL.
        """
        rows = [row(f"{y}-{str(y + 1)[-2:]}", "DET") for y in range(1970, 1979)]
        rows += [row("1979-80", "MIL"), row("1979-80", "DET")]  # reversed, as the API gave them
        rows += [row(f"{y}-{str(y + 1)[-2:]}", "MIL") for y in range(1980, 1984)]

        stints, ambiguous = build_stints(rows, team_of)
        assert teams_of(stints) == ["detroit pistons", "milwaukee bucks"]
        assert ambiguous == []

    def test_connie_hawkins(self):
        """Phoenix, then the Lakers, then Atlanta -- not PHX/LAL/PHX/LAL/ATL."""
        rows = [row(f"{y}-{str(y + 1)[-2:]}", "PHX") for y in range(1969, 1973)]
        rows += [row("1973-74", "LAL"), row("1973-74", "PHX")]  # reversed
        rows += [row("1974-75", "LAL"), row("1975-76", "ATL")]

        stints, _ = build_stints(rows, team_of)
        assert teams_of(stints) == ["phoenix suns", "los angeles lakers", "atlanta hawks"]

    def test_a_genuine_return_stays_two_stints(self):
        """The shape the game is built on must survive the fix."""
        rows = [row("2003-04", "CLE"), row("2010-11", "MIA"), row("2014-15", "CLE")]
        stints, _ = build_stints(rows, team_of)
        assert teams_of(stints) == ["cleveland cavaliers", "miami heat", "cleveland cavaliers"]
        assert stints[0]["from_season"] == 2003
        assert stints[2]["from_season"] == 2014

    def test_a_traded_season_produces_no_alternation(self):
        """Whatever order the rows arrive in, the career must not alternate."""
        from validation import implausible_problems

        for ordering in (["DET", "MIL"], ["MIL", "DET"]):
            rows = [row("1978-79", "DET"), *[row("1979-80", a) for a in ordering]]
            rows += [row("1980-81", "MIL")]
            stints, _ = build_stints(rows, team_of)
            assert not any("alternation" in p for p in implausible_problems(teams_of(stints)))

    def test_an_unorderable_season_is_reported(self):
        rows = [row("1979-80", "DET"), row("1979-80", "MIL")]
        _, ambiguous = build_stints(rows, team_of)
        assert ambiguous == [1979]

    def test_an_empty_career(self):
        assert build_stints([], team_of) == ([], [])
