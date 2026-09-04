"""Building the player pool from Basketball-Reference season data.

Replaces stats.nba.com, which scored best of anything tested and is unreachable
-- three attempts with 60-second timeouts and backoff, from a residential
machine, all failing. See docs/nba-data.md for the full evaluation.

The source is the CC0 "NBA Stats (1947-present)" dataset on Kaggle, which gives
one row per player per season per team. That shape is what the game needs, and
its team codes are already era-correct: CHH is the original Hornets, CHA the
Bobcats, CHO the Hornets since 2014, WSB the Bullets. The previous ingestion had
to infer all of that from season numbers and got Washington wrong for every
player before 1997.

What it cannot do is order a mid-season trade: both teams sit against the same
season with nothing recording which came first. career_builder narrows that using
the neighbouring seasons and reports what it cannot resolve; measured across the
whole dataset, 14.6% of multi-franchise careers stay ambiguous and belong in the
review queue rather than the rotation.
"""

from __future__ import annotations

import csv
import unicodedata
from collections import defaultdict

from career_builder import build_stints, teams_of

# Rows for a player who changed teams mid-season also include a combined total.
# Counting it would invent a franchise called "2TM".
COMBINED_TEAM_CODES = {"2TM", "3TM", "4TM", "5TM"}

# The BAA became the NBA; ABA seasons are a different league and are excluded,
# since the game's team list has no ABA franchises.
NBA_LEAGUES = {"NBA", "BAA"}

# Basketball-Reference team codes to the names the game uses. Only franchises the
# game can name are listed: a career touching anything else is skipped whole
# rather than served with a hole in it. That drops roughly a fifth of players,
# almost all pre-1980 -- Syracuse Nationals, Minneapolis Lakers, Buffalo Braves.
TEAM_CODES = {
    "ATL": "atlanta hawks",
    "BOS": "boston celtics",
    "BRK": "brooklyn nets",
    "CHA": "charlotte bobcats",
    "CHH": "charlotte hornets",
    "CHO": "charlotte hornets",
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
    "PHO": "phoenix suns",
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


def team_name_for(row):
    """The franchise the game knows, or None for one it cannot name."""
    return TEAM_CODES.get(row.get("TEAM_ABBREVIATION"))


def normalise_name(name):
    """Fold accents for matching only. The stored name keeps them.

    Willy Hernangomez is Hernangómez in this source and Hernangomez in ours,
    which is enough to make a career look absent.
    """
    folded = unicodedata.normalize("NFKD", name or "")
    return "".join(c for c in folded if not unicodedata.combining(c)).strip().lower()


def _is_nba_row(row):
    return row.get("lg") in NBA_LEAGUES and row.get("team") not in COMBINED_TEAM_CODES


def read_seasons(path):
    """{player_id: [season rows]} for NBA seasons, combined totals removed."""
    seasons = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if _is_nba_row(row):
                seasons[row["player_id"]].append(row)
    return seasons


def read_career_totals(path):
    """{player_id: {games, points, seasons}} from the per-season totals."""
    totals = defaultdict(lambda: {"games": 0, "points": 0, "seasons": set()})
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not _is_nba_row(row):
                continue
            entry = totals[row["player_id"]]
            entry["games"] += int(row.get("g") or 0)
            entry["points"] += int(row.get("pts") or 0)
            entry["seasons"].add(row["season"])
    return totals


def read_all_star_counts(path):
    """{player_id: selections}. A far better fame signal than scoring average."""
    counts = defaultdict(int)
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            # `replaced` marks a selection someone did not actually take up.
            if row.get("lg") in NBA_LEAGUES and (row.get("replaced") or "").upper() != "TRUE":
                counts[row["player_id"]] += 1
    return counts


def build_player(player_id, season_rows, totals=None, all_star_selections=0):
    """One player's career, or None if any franchise cannot be named.

    Skipping the whole career is deliberate: a puzzle missing a stop is worse
    than no puzzle, because it is unwinnable in a way the player cannot see.
    """
    rows = [
        {"SEASON_ID": r["season"], "TEAM_ABBREVIATION": r["team"], "G": r.get("g")}
        for r in season_rows
    ]
    if any(team_name_for(r) is None for r in rows):
        return None

    stints, ambiguous = build_stints(rows, team_name_for)
    if not stints:
        return None

    totals = totals or {}
    games = totals.get("games", 0)
    points = totals.get("points", 0)

    return {
        "id": player_id,
        "name": season_rows[0]["player"],
        "teams": teams_of(stints),
        "stints": stints,
        "games": games,
        "ppg": round(points / games, 1) if games else 0.0,
        "seasons_played": len(totals.get("seasons", ())) or None,
        "all_star_selections": all_star_selections,
        # Reported rather than hidden: a season whose trade order could not be
        # resolved is exactly what a reviewer should look at.
        "ambiguous_seasons": ambiguous or None,
    }


def build_pool(seasons_path, totals_path=None, all_star_path=None):
    """Every career the game can name, with the signals difficulty needs."""
    seasons = read_seasons(seasons_path)
    totals = read_career_totals(totals_path) if totals_path else {}
    all_stars = read_all_star_counts(all_star_path) if all_star_path else {}

    players = []
    skipped = 0
    for player_id, rows in seasons.items():
        player = build_player(
            player_id,
            sorted(rows, key=lambda r: r["season"]),
            totals=totals.get(player_id),
            all_star_selections=all_stars.get(player_id, 0),
        )
        if player is None:
            skipped += 1
            continue
        players.append(player)

    return players, skipped
