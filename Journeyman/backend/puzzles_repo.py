"""Scheduling the daily puzzle.

Replaces `md5(date) % len(players)`, where the pool size is part of the key --
so adding or removing a single player rewrites which player every future date
resolves to, including dates already announced. Promoting seven flagged careers
out of the rotation was enough to reshuffle the entire schedule.

Scheduled rows fix that and buy three things the hash could never give:
no repeats, a puzzle that cannot shift mid-day once written, and an archive to
sell later.
"""

from __future__ import annotations

import random
from datetime import timedelta

TABLE = "puzzles"

# A player scheduled inside this window is not eligible again. Roughly half a
# year: long enough that nobody recognises a repeat, short enough that a pool of
# a few hundred can fill the calendar.
REPEAT_WINDOW_DAYS = 180


class NotEnoughPlayers(RuntimeError):
    """The eligible pool cannot fill the requested days without repeating."""


def payload_for(player):
    """What a session needs, denormalised.

    Copied rather than referenced so correcting a player record later cannot
    silently change a puzzle that has already been played.
    """
    return {
        "player_id": player["id"],
        "player_name": player["name"],
        "teams": list(player["teams"]),
    }


class PuzzlesRepo:
    def __init__(self, client, game_slug="journeyman"):
        self._client = client
        self._game_slug = game_slug

    def _table(self):
        return self._client.table(TABLE)

    def get(self, puzzle_date):
        response = (
            self._table()
            .select("puzzle_date,player_id,payload")
            .eq("game_slug", self._game_slug)
            .eq("puzzle_date", str(puzzle_date))
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    def schedule(self, puzzle_date, player):
        """Write one day's puzzle. Upsert, so re-running is harmless."""
        self._table().upsert(
            {
                "game_slug": self._game_slug,
                "puzzle_date": str(puzzle_date),
                "player_id": player["id"],
                "payload": payload_for(player),
            },
            on_conflict="game_slug,puzzle_date",
        ).execute()

    def scheduled_between(self, start, end):
        """Existing rows in a date range, keyed by date."""
        response = (
            self._table()
            .select("puzzle_date,player_id,payload")
            .eq("game_slug", self._game_slug)
            .gte("puzzle_date", str(start))
            .lte("puzzle_date", str(end))
            .execute()
        )
        return {row["puzzle_date"]: row for row in (response.data or [])}

    def recently_used_ids(self, before, window_days=REPEAT_WINDOW_DAYS):
        """Players used recently enough that reusing one would feel like a repeat."""
        response = (
            self._table()
            .select("player_id")
            .eq("game_slug", self._game_slug)
            .gte("puzzle_date", str(before - timedelta(days=window_days)))
            .execute()
        )
        return {row["player_id"] for row in (response.data or []) if row["player_id"]}


def plan(pool, start, days, already_scheduled=None, recently_used=None, rng=None):
    """Choose a player for each unscheduled date in the window.

    Pure, so the no-repeat rules are testable without a database.

    Existing rows are never overwritten: a puzzle already scheduled is a promise,
    and quietly changing it is the behaviour this replaces.
    """
    rng = rng or random.Random()
    already_scheduled = already_scheduled or {}
    used = set(recently_used or set())

    # Anything already on the calendar is spoken for, and its player used.
    for row in already_scheduled.values():
        if row.get("player_id"):
            used.add(row["player_id"])

    eligible = [p for p in pool if p["id"] not in used]
    open_dates = [
        start + timedelta(days=offset)
        for offset in range(days)
        if str(start + timedelta(days=offset)) not in already_scheduled
    ]

    if len(eligible) < len(open_dates):
        raise NotEnoughPlayers(
            f"{len(open_dates)} days to fill but only {len(eligible)} players not "
            f"used in the last {REPEAT_WINDOW_DAYS} days. Promote more players, "
            f"or schedule a shorter window."
        )

    rng.shuffle(eligible)
    return list(zip(open_dates, eligible[: len(open_dates)], strict=False))
