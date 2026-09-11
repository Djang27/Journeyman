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

    PAGE_SIZE = 1000

    def scheduled_between(self, start, end):
        """Existing rows in a date range, keyed by date.

        Paged, because PostgREST caps a response at 1000 rows and says nothing
        about it. The scheduler only ever asks for ninety days, but the archive
        asks for launch-to-yesterday, which grows by one row a day -- so this
        would have started silently losing the oldest puzzles somewhere around
        the third year, with no error anywhere.
        """
        rows = {}
        offset = 0
        while True:
            response = (
                self._table()
                .select("puzzle_date,player_id,payload")
                .eq("game_slug", self._game_slug)
                .gte("puzzle_date", str(start))
                .lte("puzzle_date", str(end))
                .order("puzzle_date")
                .range(offset, offset + self.PAGE_SIZE - 1)
                .execute()
            )
            page = response.data or []
            rows.update({row["puzzle_date"]: row for row in page})
            if len(page) < self.PAGE_SIZE:
                return rows
            offset += self.PAGE_SIZE

    def unschedule_after(self, day):
        """Delete every puzzle scheduled strictly after `day`. Returns the count.

        For redoing a calendar that was filled under rules since changed. The
        cutoff is strict, and the caller is expected to pass today: a future
        puzzle is a promise nobody has been shown, while today's may be halfway
        through being played and the past is the archive, which people have
        paid for.

        Deliberately not a general delete. The one dangerous version of this
        operation is the one that takes an arbitrary range.
        """
        response = (
            self._table()
            .delete()
            .eq("game_slug", self._game_slug)
            .gt("puzzle_date", str(day))
            .execute()
        )
        return len(response.data or [])

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


def plan(
    pool, start, days, already_scheduled=None, last_used=None, rng=None, prefer=None, fit=None
):
    """Choose a player for each unscheduled date in the window.

    Pure, so the rules are testable without a database.

    Players are ranked by how long ago they were last used, never-used first,
    and the least recently used fill the calendar. That always succeeds while the
    pool can cover the horizon, and spaces repeats as widely as the pool allows
    -- which hard exclusion cannot do once the calendar is deeper than the pool.

    `prefer` marks players better suited to the slot, as a yes or no. `fit` is
    the graded form: `fit(player, date)` returns a cost for putting that player
    on that date, lower being better, which is what a difficulty curve across
    the week needs -- Monday and Saturday want different players, so a single
    ranking of the pool cannot express it.

    Either way the preference is soft. Widening beats failing: a hard filter
    that cannot fill the horizon leaves days empty, and an empty day is a
    broken game while a slightly-off day is only a slightly-off day.

    With `fit`, dates are filled in order and each takes the best remaining
    player -- best fit first, and among equal fits the one used longest ago.
    That is greedy rather than optimal, which is the right trade here: the
    alternative is an assignment problem solved every time the calendar is
    topped up, to place puzzles nobody will notice were placed one slot better.

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

    if fit is not None:
        # Recency is now the tie-break rather than the ranking, so it is frozen
        # here as a position and read from inside the loop.
        recency = {id(p): rank for rank, p in enumerate(candidates)}
        remaining = list(candidates)
        chosen = []
        for date in open_dates:
            if not remaining:
                break
            best = min(remaining, key=lambda p: (fit(p, date), recency[id(p)]))
            remaining.remove(best)
            chosen.append((date, best))
        return chosen

    if prefer is not None:
        preferred = [p for p in candidates if prefer(p)]
        rest = [p for p in candidates if not prefer(p)]
        candidates = preferred + rest

    return list(zip(open_dates, candidates[: len(open_dates)], strict=False))
