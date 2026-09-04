"""Turning season rows into an ordered career.

This is where the pre-1985 bug lived. The old code walked `SeasonTotalsRegularSeason`
in whatever order the API happened to return and collapsed consecutive duplicates,
which produced careers like:

    Bob Lanier      DET / MIL / DET / MIL          (he went DET then MIL)
    Connie Hawkins  PHX / LAL / PHX / LAL / ATL    (PHX, LAL, ATL)

A player traded mid-season has two rows for that season, and nothing guarantees
they arrive in the order he actually played. Sorting by season fixes the easy
half; the hard half is ordering *within* a season, which the endpoint does not
state.

The trick is that neighbouring seasons say which came first. A player traded in
February was with the team he also played the previous season, and continues with
the team he plays the next one. That resolves the common case, and where it
cannot, the ambiguity is reported rather than guessed at.
"""

from __future__ import annotations

TOTALS_TEAM = "TOT"  # the NBA's combined row for a multi-team season


def season_start_year(season_id):
    """'1979-80' or '21979' -> 1979. Returns None when unparseable."""
    text = str(season_id or "")
    for start in (0, 1):  # some endpoints prefix a league digit
        candidate = text[start : start + 4]
        if candidate.isdigit():
            year = int(candidate)
            if 1940 <= year <= 2100:
                return year
    return None


def group_by_season(rows, team_of):
    """{season_year: [team, ...]} with combined rows and unknown teams dropped."""
    seasons = {}
    for row in rows:
        if row.get("TEAM_ABBREVIATION") == TOTALS_TEAM:
            continue

        year = season_start_year(row.get("SEASON_ID"))
        team = team_of(row)
        if year is None or not team:
            continue

        teams = seasons.setdefault(year, [])
        if team not in teams:
            teams.append(team)

    return seasons


def order_within_season(teams, previous, following):
    """Order one season's teams using the seasons either side.

    A player traded mid-season keeps playing for whoever he is with next season,
    and was with whoever he played for last season. Anything neither says stays
    in the order it arrived, which is the best available answer.
    """
    if len(teams) < 2:
        return list(teams), False

    carried_in = [t for t in teams if t in previous]
    carried_out = [t for t in teams if t in following]
    middle = [t for t in teams if t not in carried_in and t not in carried_out]

    ordered = carried_in + middle + [t for t in carried_out if t not in carried_in]

    # Ambiguous when the neighbours settle nothing: no team continues in either
    # direction, so the order within the season is a guess.
    ambiguous = not carried_in and not carried_out
    return ordered, ambiguous


def build_stints(rows, team_of):
    """Rows -> ordered stints with seasons, plus anything that stayed ambiguous.

    Returns (stints, ambiguous_seasons). A stint is
    {"team": ..., "from_season": year, "to_season": year}, and a return to a
    former franchise is a separate stint -- that repetition is the puzzle.
    """
    seasons = group_by_season(rows, team_of)
    years = sorted(seasons)

    ordered_teams = []
    ambiguous = []
    for index, year in enumerate(years):
        previous = seasons[years[index - 1]] if index else []
        following = seasons[years[index + 1]] if index + 1 < len(years) else []

        teams, is_ambiguous = order_within_season(seasons[year], previous, following)
        if is_ambiguous:
            ambiguous.append(year)

        for team in teams:
            ordered_teams.append((year, team))

    stints = []
    for year, team in ordered_teams:
        if stints and stints[-1]["team"] == team:
            stints[-1]["to_season"] = year
        else:
            stints.append({"team": team, "from_season": year, "to_season": year})

    return stints, ambiguous


def teams_of(stints):
    return [stint["team"] for stint in stints]
