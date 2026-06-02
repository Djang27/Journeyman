import json
import random
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


NBA_STATS_BASE_URL = "https://stats.nba.com/stats"
PLAYER_DATABASE_PATH = Path(__file__).with_name("nba_players.json")
TARGET_PLAYER_COUNT = 120
MIN_PLAYER_COUNT = 40
REQUEST_DELAY_SECONDS = 0.6

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
    "CHA": "charlotte hornets",
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
    "NOK": "new orleans/oklahoma city hornets",
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
            return [dict(zip(headers, row)) for row in result["rowSet"]]

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


def career_teams_for_player(player_id):
    data = nba_get(
        "playercareerstats",
        {
            "LeagueID": "00",
            "PerMode": "Totals",
            "PlayerID": player_id,
        },
    )

    teams = []

    for row in result_set(data, "SeasonTotalsRegularSeason"):
        abbr = row.get("TEAM_ABBREVIATION")

        if abbr == "TOT":
            continue

        team_name = TEAM_NAMES_BY_ABBR.get(abbr)

        if not team_name:
            return []

        if not teams or teams[-1] != team_name:
            teams.append(team_name)

    return teams


def build_player_database():
    candidates = [
        player
        for player in all_nba_players()
        if player.get("GAMES_PLAYED_FLAG") == "Y"
    ]
    random.shuffle(candidates)

    players = []

    for candidate in candidates:
        if len(players) >= TARGET_PLAYER_COUNT:
            break

        teams = career_teams_for_player(candidate["PERSON_ID"])

        if len(teams) >= 2 and len(set(teams)) >= 2:
            players.append(
                {
                    "id": candidate["PERSON_ID"],
                    "name": candidate["DISPLAY_FIRST_LAST"],
                    "teams": teams,
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


if __name__ == "__main__":
    database = build_player_database()

    with PLAYER_DATABASE_PATH.open("w", encoding="utf-8") as player_file:
        json.dump(database, player_file, indent=2, sort_keys=True)

    print(f"\nWrote {len(database['players'])} players to {PLAYER_DATABASE_PATH}")
