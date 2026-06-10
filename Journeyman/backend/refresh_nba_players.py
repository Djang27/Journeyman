import json
import random
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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


def career_stats_for_player(player_id):
    """Returns (teams, career_ppg). teams is empty list if player is invalid."""
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
            return [], 0.0

        if not teams or teams[-1] != team_name:
            teams.append(team_name)

    career_rows = result_set(data, "CareerTotalsRegularSeason")
    if career_rows:
        total_pts = career_rows[0].get("PTS", 0) or 0
        total_gp = career_rows[0].get("GP", 0) or 0
        career_ppg = round(total_pts / total_gp, 1) if total_gp > 0 else 0.0
    else:
        career_ppg = 0.0

    return teams, career_ppg


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

        teams, ppg = career_stats_for_player(candidate["PERSON_ID"])

        if len(teams) >= 2 and len(set(teams)) >= 2 and ppg >= MIN_CAREER_PPG:
            players.append(
                {
                    "id": candidate["PERSON_ID"],
                    "name": candidate["DISPLAY_FIRST_LAST"],
                    "ppg": ppg,
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


def filter_existing_database():
    """Re-check career PPG for every player in the current database and drop those below MIN_CAREER_PPG."""
    with PLAYER_DATABASE_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    existing = data.get("players", [])
    print(f"Checking {len(existing)} existing players (min PPG: {MIN_CAREER_PPG})...")

    kept = []
    for player in existing:
        _, ppg = career_stats_for_player(player["id"])
        status = "KEEP" if ppg >= MIN_CAREER_PPG else "DROP"
        safe_name = player['name'].encode('ascii', errors='replace').decode()
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
