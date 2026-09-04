"""Team reference data shared by the game rules.

The conference map exists server-side because the hint reveals it. Deriving it
in the browser -- as team_list.js did -- required the client to hold the answer,
which is exactly what Phase 0 removes.

Kept in step with the CONFERENCE map in frontend/src/components/team_list.js;
tests/test_teams.py asserts the two agree.
"""

CONFERENCES = {
    "atlanta hawks": "East",
    "boston celtics": "East",
    "brooklyn nets": "East",
    "charlotte bobcats": "East",
    "charlotte hornets": "East",
    "chicago bulls": "East",
    "cleveland cavaliers": "East",
    "dallas mavericks": "West",
    "denver nuggets": "West",
    "detroit pistons": "East",
    "golden state warriors": "West",
    "houston rockets": "West",
    "indiana pacers": "East",
    "los angeles clippers": "West",
    "los angeles lakers": "West",
    "memphis grizzlies": "West",
    "miami heat": "East",
    "milwaukee bucks": "East",
    "minnesota timberwolves": "West",
    "new jersey nets": "East",
    "new orleans hornets": "West",
    "new orleans pelicans": "West",
    "new york knicks": "East",
    "oklahoma city thunder": "West",
    "orlando magic": "East",
    "philadelphia 76ers": "East",
    "phoenix suns": "West",
    "portland trail blazers": "West",
    "sacramento kings": "West",
    "san antonio spurs": "West",
    "seattle supersonics": "West",
    "toronto raptors": "East",
    "utah jazz": "West",
    "vancouver grizzlies": "West",
    "washington bullets": "East",
    "washington wizards": "East",
}


def conference(team):
    """East or West, or None for a team the map does not know."""
    return CONFERENCES.get(team.strip().lower()) if team else None
