import json
import random
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from career_builder import build_stints, season_start_year, teams_of

NBA_STATS_BASE_URL = "https://stats.nba.com/stats"
PLAYER_DATABASE_PATH = Path(__file__).with_name("nba_players.json")
TARGET_PLAYER_COUNT = 200
MIN_PLAYER_COUNT = 40
REQUEST_DELAY_SECONDS = 0.6
MIN_CAREER_PPG = 5.0

NBA_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.nba.com/",
}

TEAM_NAMES_BY_ABBR = {
    "ATL": "atlanta hawks",
    "BKN": "brooklyn nets",
    "BOS": "boston celtics",
    "CHH": "charlotte hornets",
    "CHI": "chicago bulls",
    "CLE": "cleveland cavaliers",
    "DAL": "dallas mavericks",
    "DEN": "denver nuggets",
    "DET": "detroit pistons",
    "GSW": "golden state warriors",
    "HOU": "houston rockets",
    "IND": "indiana pacers",
    "LAC": "los angeles clippers",
    "LAL": "los angeles lakers",
    "MEM": "memphis grizzlies",
    "MIA": "miami heat",
    "MIL": "milwaukee bucks",
    "MIN": "minnesota timberwolves",
    "NJN": "new jersey nets",
    "NOH": "new orleans hornets",
    "NOK": "new orleans hornets",
    "NOP": "new orleans pelicans",
    "NYK": "new york knicks",
    "OKC": "oklahoma city thunder",
    "ORL": "orlando magic",
    "PHI": "philadelphia 76ers",
    "PHX": "phoenix suns",
    "POR": "portland trail blazers",
    "SAC": "sacramento kings",
    "SAS": "san antonio spurs",
    "SEA": "seattle supersonics",
    "TOR": "toronto raptors",
    "UTA": "utah jazz",
    "VAN": "vancouver grizzlies",
    "WAS": "washington wizards",
    "WSB": "washington bullets",
}


def current_nba_season():
    today = datetime.now()
    start_year = today.year if today.month >= 10 else today.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def nba_get(endpoint, params):
    url = f"{NBA_STATS_BASE_URL}/{endpoint}?{urlencode(params)}"
    request = Request(url, headers=NBA_HEADERS)

    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def result_set(data, name):
    for result in data.get("resultSets", []):
        if result.get("name") == name:
            headers = result["headers"]
            # strict=True: a row whose length does not match the headers means
            # the upstream response shape changed, which should fail loudly
            # rather than silently drop columns.
            return [dict(zip(headers, row, strict=True)) for row in result["rowSet"]]

    return []


def all_nba_players():
    data = nba_get(
        "commonallplayers",
        {
            "IsOnlyCurrentSeason": "0",
            "LeagueID": "00",
            "Season": current_nba_season(),
        },
    )
    return result_set(data, "CommonAllPlayers")


# Franchises that kept an abbreviation through a rename, so the era has to be
# read from the season rather than the code. Each entry is the season from which
# the newer name applies.
#
# Getting this wrong is invisible until someone checks: the shipped pool contains
# no "washington bullets" at all, across players going back to the 1970s, because
# WAS mapped to Wizards regardless of year.
# Each entry is (season the name took effect, name), newest first. Charlotte
# needs three because the name came back: the original Hornets left for New
# Orleans in 2002, the Bobcats arrived in 2004, and they took the Hornets name
# in 2014. A two-way split would call a 1990s Charlotte season "Bobcats".
ERA_NAMES = {
    "CHA": ((2014, "charlotte hornets"), (2004, "charlotte bobcats"), (0, "charlotte hornets")),
    "WAS": ((1997, "washington wizards"), (0, "washington bullets")),
}


def team_name_for(row):
    """The franchise as it was called that season, or None if unrecognised."""
    abbr = row.get("TEAM_ABBREVIATION")
    era = ERA_NAMES.get(abbr)

    if era:
        # season_start_year rather than SEASON_ID[:4]: the endpoint sometimes
        # prefixes a league digit, so "22013" sliced naively reads as year 2201
        # and every era test silently takes the wrong branch.
        year = season_start_year(row.get("SEASON_ID"))
        if year is None:
            return era[0][1]  # unreadable season: assume the current name
        for from_season, name in era:
            if year >= from_season:
                return name

    return TEAM_NAMES_BY_ABBR.get(abbr)


def career_stats_for_player(player_id):
    """Returns (stints, career_ppg, ambiguous_seasons).

    Stints carry seasons, and ordering is handled by career_builder rather than
    by walking the API's row order -- which is what produced Bob Lanier as
    DET / MIL / DET / MIL.
    """
    data = nba_get(
        "playercareerstats",
        {
            "LeagueID": "00",
            "PerMode": "Totals",
            "PlayerID": player_id,
        },
    )

    rows = result_set(data, "SeasonTotalsRegularSeason")

    # A team we cannot name means a career we cannot state correctly -- an ABA
    # or international row, say. Better to skip the player than to serve a puzzle
    # with a hole in it.
    for row in rows:
        if row.get("TEAM_ABBREVIATION") != "TOT" and not team_name_for(row):
            return [], 0.0, []

    stints, ambiguous = build_stints(rows, team_name_for)

    career_rows = result_set(data, "CareerTotalsRegularSeason")
    if career_rows:
        total_pts = career_rows[0].get("PTS", 0) or 0
        total_gp = career_rows[0].get("GP", 0) or 0
        career_ppg = round(total_pts / total_gp, 1) if total_gp > 0 else 0.0
    else:
        career_ppg = 0.0

    return stints, career_ppg, ambiguous


def build_player_database():
    candidates = [player for player in all_nba_players() if player.get("GAMES_PLAYED_FLAG") == "Y"]
    random.shuffle(candidates)

    players = []

    for candidate in candidates:
        if len(players) >= TARGET_PLAYER_COUNT:
            break

        stints, ppg, ambiguous = career_stats_for_player(candidate["PERSON_ID"])
        teams = teams_of(stints)

        if len(teams) >= 2 and len(set(teams)) >= 2 and ppg >= MIN_CAREER_PPG:
            players.append(
                {
                    "id": candidate["PERSON_ID"],
                    "name": candidate["DISPLAY_FIRST_LAST"],
                    "ppg": ppg,
                    "teams": teams,
                    "stints": stints,
                    # Recorded rather than hidden: a season the neighbours could
                    # not order is exactly what a reviewer should look at.
                    "ambiguous_seasons": ambiguous or None,
                }
            )

        print(f"Found {len(players)} players...", end="\r")
        time.sleep(REQUEST_DELAY_SECONDS)

    if len(players) < MIN_PLAYER_COUNT:
        raise RuntimeError("Could not build enough NBA journeyman players.")

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "season": current_nba_season(),
        "source": "stats.nba.com",
        "players": players,
    }


def filter_existing_database():
    """Re-check career PPG for every player in the database, dropping those below MIN_CAREER_PPG."""
    with PLAYER_DATABASE_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    existing = data.get("players", [])
    print(f"Checking {len(existing)} existing players (min PPG: {MIN_CAREER_PPG})...")

    kept = []
    for player in existing:
        _, ppg, _ = career_stats_for_player(player["id"])
        status = "KEEP" if ppg >= MIN_CAREER_PPG else "DROP"
        safe_name = player["name"].encode("ascii", errors="replace").decode()
        print(f"  [{status}] {safe_name}: {ppg} PPG")
        if ppg >= MIN_CAREER_PPG:
            player["ppg"] = ppg
            kept.append(player)
        time.sleep(REQUEST_DELAY_SECONDS)

    data["players"] = kept
    data["filtered_at"] = datetime.now().isoformat(timespec="seconds")

    with PLAYER_DATABASE_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)

    print(f"\nKept {len(kept)}/{len(existing)} players with >= {MIN_CAREER_PPG} PPG")


if __name__ == "__main__":
    import sys

    if "--filter" in sys.argv:
        filter_existing_database()
    else:
        database = build_player_database()
        with PLAYER_DATABASE_PATH.open("w", encoding="utf-8") as player_file:
            json.dump(database, player_file, indent=2, sort_keys=True)
        print(f"\nWrote {len(database['players'])} players to {PLAYER_DATABASE_PATH}")
