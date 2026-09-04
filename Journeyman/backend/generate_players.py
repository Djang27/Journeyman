"""Choosing which player a game is about.

The pool comes from the `players` table when a database is configured, and from
nba_players.json otherwise. The file is the fallback for degraded mode, not the
source of truth: only the table carries the curation gate, so only the table can
keep a career flagged for review out of the rotation.

The pool is cached for a short while. Player data changes when an import runs,
which is weekly at most, so re-reading it per request would cost a round trip to
learn nothing.
"""

import hashlib
import json
import random
import threading
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PLAYER_DATABASE_PATH = Path(__file__).with_name("nba_players.json")

# How long a fetched pool is reused. Short enough that promoting a player takes
# effect within minutes, long enough that the hot path is not a database call.
POOL_CACHE_SECONDS = 300

_pool_source = None
_cache = {"players": None, "fetched_at": 0.0}
_cache_lock = threading.Lock()


def use_pool_source(fetch):
    """Point selection at a live pool. `fetch` returns a list of player dicts.

    Called once at startup. Passing None restores the bundled JSON, which is
    what the tests and a database-less local run use.
    """
    global _pool_source
    with _cache_lock:
        _pool_source = fetch
        _cache["players"] = None
        _cache["fetched_at"] = 0.0


LAUNCH_DATE = date(2026, 6, 11)
EASTERN = ZoneInfo("America/New_York")


def _eastern_today():
    return datetime.now(EASTERN).date()


def _load_from_file():
    with PLAYER_DATABASE_PATH.open("r", encoding="utf-8") as player_file:
        data = json.load(player_file)

    players = data.get("players", [])

    if not players:
        raise RuntimeError("The NBA player database is empty.")

    return players


def _load_players():
    """The active pool, cached. Falls back to the file if the database fails.

    A database that is briefly unreachable degrades the pool rather than the
    game: players keep playing from the bundled file, which is the same
    fallback promised for every other outage.
    """
    if _pool_source is None:
        return _load_from_file()

    with _cache_lock:
        fresh = time.monotonic() - _cache["fetched_at"] < POOL_CACHE_SECONDS
        if _cache["players"] and fresh:
            return _cache["players"]

    try:
        players = _pool_source()
    except Exception:
        return _load_from_file()

    if not players:
        # An empty active pool means nobody has been promoted yet. Falling back
        # keeps the game playable rather than failing every request.
        return _load_from_file()

    with _cache_lock:
        _cache["players"] = players
        _cache["fetched_at"] = time.monotonic()

    return players


def today_eastern():
    """Public wrapper. Delegates so tests patching _eastern_today still apply."""
    return _eastern_today()


def day_number():
    return (_eastern_today() - LAUNCH_DATE).days + 1


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
    today_str = _eastern_today().isoformat()
    index = int(hashlib.md5(today_str.encode()).hexdigest(), 16) % len(players)
    player = players[index]
    return player["name"], player["teams"], player["id"], day_number()
