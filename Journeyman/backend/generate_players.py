import json
import os
import random
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


NBA_STATS_BASE_URL = "https://stats.nba.com/stats"
CACHE_DIRECTORY = Path(tempfile.gettempdir()) if os.getenv("VERCEL") else Path(__file__).parent
CACHE_PATH = CACHE_DIRECTORY / "nba_player_cache.json"
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
MIN_CACHED_PLAYERS = 40
TARGET_CACHE_SIZE = 120
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


def _current_nba_season():
    today = datetime.now()
    start_year = today.year if today.month >= 10 else today.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def _nba_get(endpoint, params):
    url = f"{NBA_STATS_BASE_URL}/{endpoint}?{urlencode(params)}"
    request = Request(url, headers=NBA_HEADERS)

    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _result_set(data, name):
    for result_set in data.get("resultSets", []):
        if result_set.get("name") == name:
            headers = result_set["headers"]
            return [dict(zip(headers, row)) for row in result_set["rowSet"]]

    return []


def _load_cache():
    if not CACHE_PATH.exists():
        return {"created_at": 0, "season": _current_nba_season(), "players": []}

    try:
        with CACHE_PATH.open("r", encoding="utf-8") as cache_file:
            return json.load(cache_file)
    except (json.JSONDecodeError, OSError):
        return {"created_at": 0, "season": _current_nba_season(), "players": []}


def _save_cache(cache):
    with CACHE_PATH.open("w", encoding="utf-8") as cache_file:
        json.dump(cache, cache_file, indent=2, sort_keys=True)


def _cache_is_fresh(cache):
    age = time.time() - cache.get("created_at", 0)
    return (
        age < CACHE_TTL_SECONDS
        and cache.get("season") == _current_nba_season()
        and len(cache.get("players", [])) >= MIN_CACHED_PLAYERS
    )


def _all_nba_players():
    data = _nba_get(
        "commonallplayers",
        {
            "IsOnlyCurrentSeason": "0",
            "LeagueID": "00",
            "Season": _current_nba_season(),
        },
    )
    return _result_set(data, "CommonAllPlayers")


def _career_teams_for_player(player_id):
    data = _nba_get(
        "playercareerstats",
        {
            "LeagueID": "00",
            "PerMode": "Totals",
            "PlayerID": player_id,
        },
    )

    rows = _result_set(data, "SeasonTotalsRegularSeason")
    teams = []

    for row in rows:
        abbr = row.get("TEAM_ABBREVIATION")

        if abbr == "TOT":
            continue

        team_name = TEAM_NAMES_BY_ABBR.get(abbr)

        if not team_name:
            return []

        if not teams or teams[-1] != team_name:
            teams.append(team_name)

    return teams


def _refresh_cache():
    players = [
        player
        for player in _all_nba_players()
        if player.get("GAMES_PLAYED_FLAG") == "Y"
    ]
    random.shuffle(players)

    journeymen = []

    for player in players:
        if len(journeymen) >= TARGET_CACHE_SIZE:
            break

        teams = _career_teams_for_player(player["PERSON_ID"])
        unique_teams = set(teams)

        if len(teams) >= 2 and len(unique_teams) >= 2:
            journeymen.append(
                {
                    "id": player["PERSON_ID"],
                    "name": player["DISPLAY_FIRST_LAST"],
                    "teams": teams,
                }
            )

        time.sleep(REQUEST_DELAY_SECONDS)

    if len(journeymen) < MIN_CACHED_PLAYERS:
        raise RuntimeError("Could not build enough NBA journeyman players from NBA Stats.")

    cache = {
        "created_at": time.time(),
        "season": _current_nba_season(),
        "source": "stats.nba.com",
        "players": journeymen,
    }
    _save_cache(cache)
    return cache


def randomPlayer():
    cache = _load_cache()

    if not _cache_is_fresh(cache):
        cache = _refresh_cache()

    player = random.choice(cache["players"])
    return player["name"], player["teams"]
