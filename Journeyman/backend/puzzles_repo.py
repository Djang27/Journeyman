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

# How far back to look when deciding who is "recently used". Players seen inside
# this window are avoided if the pool allows it -- but never at the cost of
# failing to schedule, because a pool smaller than the window plus the horizon
# makes hard exclusion arithmetically impossible.
#
# With 193 promoted players, filling 90 days while excluding 180 days of history
# would need 270 distinct players. Ranking by least-recently-used instead always
# succeeds and spaces repeats as widely as the pool permits.
REPEAT_WINDOW_DAYS = 365


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

    def last_used(self, before, window_days=REPEAT_WINDOW_DAYS):
        """{player_id: most recent puzzle_date} within the look-back window.

        Dates rather than a set, because the scheduler ranks by how long ago a
        player was used rather than excluding outright.
        """
        response = (
            self._table()
            .select("player_id,puzzle_date")
            .eq("game_slug", self._game_slug)
            .gte("puzzle_date", str(before - timedelta(days=window_days)))
            .execute()
        )

        seen = {}
        for row in response.data or []:
            player_id = row["player_id"]
            if player_id is None:
                continue
            date = row["puzzle_date"]
            if player_id not in seen or date > seen[player_id]:
                seen[player_id] = date
        return seen


def plan(pool, start, days, already_scheduled=None, last_used=None, rng=None):
    """Choose a player for each unscheduled date in the window.

    Pure, so the rules are testable without a database.

    Players are ranked by how long ago they were last used, never-used first,
    and the least recently used fill the calendar. That always succeeds while the
    pool can cover the horizon, and spaces repeats as widely as the pool allows
    -- which hard exclusion cannot do once the calendar is deeper than the pool.

    Existing rows are never overwritten: a puzzle already scheduled is a promise,
    and quietly changing it is the behaviour this replaces.
    """
    rng = rng or random.Random()
    already_scheduled = already_scheduled or {}
    last_used = dict(last_used or {})

    # Anything already on the calendar counts as used, at its own date.
    for date, row in already_scheduled.items():
        player_id = row.get("player_id")
        if player_id and date > last_used.get(player_id, ""):
            last_used[player_id] = date

    open_dates = [
        start + timedelta(days=offset)
        for offset in range(days)
        if str(start + timedelta(days=offset)) not in already_scheduled
    ]

    if len(pool) < len(open_dates):
        raise NotEnoughPlayers(
            f"{len(open_dates)} days to fill but only {len(pool)} players in the "
            f"pool. Promote more players, or schedule a shorter window."
        )

    # Shuffle first so players never used -- who all rank equally -- come out in
    # a different order each run rather than by database order.
    candidates = list(pool)
    rng.shuffle(candidates)
    candidates.sort(key=lambda p: last_used.get(p["id"], ""))

    return list(zip(open_dates, candidates[: len(open_dates)], strict=False))
