import json
import random
from pathlib import Path


PLAYER_DATABASE_PATH = Path(__file__).with_name("nba_players.json")


def _load_players():
    with PLAYER_DATABASE_PATH.open("r", encoding="utf-8") as player_file:
        data = json.load(player_file)

    players = data.get("players", [])

    if not players:
        raise RuntimeError("The NBA player database is empty.")

    return players


def randomPlayer(exclude_ids=None):
    players = _load_players()

    available = players
    if exclude_ids:
        filtered = [p for p in players if p["id"] not in exclude_ids]
        available = filtered if filtered else players  # reset when all have been seen

    player = random.choice(available)
    return player["name"], player["teams"], player["id"]
