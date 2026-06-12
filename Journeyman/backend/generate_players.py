import hashlib
import json
import random
from datetime import date
from pathlib import Path


PLAYER_DATABASE_PATH = Path(__file__).with_name("nba_players.json")
LAUNCH_DATE = date(2026, 6, 11)


def _load_players():
    with PLAYER_DATABASE_PATH.open("r", encoding="utf-8") as player_file:
        data = json.load(player_file)

    players = data.get("players", [])

    if not players:
        raise RuntimeError("The NBA player database is empty.")

    return players


def day_number():
    return (date.today() - LAUNCH_DATE).days + 1


def randomPlayer(exclude_ids=None):
    players = _load_players()

    available = players
    if exclude_ids:
        filtered = [p for p in players if p["id"] not in exclude_ids]
        available = filtered if filtered else players  # reset when all have been seen

    player = random.choice(available)
    return player["name"], player["teams"], player["id"]


def daily_player():
    players = _load_players()
    today_str = date.today().isoformat()
    index = int(hashlib.md5(today_str.encode()).hexdigest(), 16) % len(players)
    player = players[index]
    return player["name"], player["teams"], player["id"], day_number()
