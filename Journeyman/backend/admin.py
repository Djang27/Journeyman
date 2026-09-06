"""Operator tools, and the switch that takes the game down deliberately.

Written for the morning a bad puzzle ships. That morning you want to swap
tomorrow's puzzle and remove today's results, and you want it to take a minute
rather than an afternoon of hand-written SQL against production.

## On degraded mode

The roadmap promised "writes off, daily still playable". That is not achievable
any more, and saying so is better than shipping something that pretends
otherwise: since Phase 0 every game start writes a session row, because the
server has to hold the answer somewhere. Postgres being down means the game is
down.

What is achievable is failing *honestly*. A deliberate maintenance mode returns
503 and a message a person can read, rather than the 500s and blank screens an
unplanned outage produces. That is the difference between "we are working on it"
and "this is broken and nobody knows".

## On the admin credential

A single shared token, checked in constant time. Not a user role, because there
is one operator and building an authorisation system for one person is how a
weekend disappears. It is a real credential: without ADMIN_TOKEN set, every
admin route is closed rather than open.
"""

from __future__ import annotations

import hmac


class AdminError(Exception):
    """The caller may not do this."""


def is_authorised(supplied_token, configured_token):
    """Constant-time comparison, and closed when unconfigured.

    An unset token must mean "nobody", not "everybody" -- the opposite default
    is how an admin endpoint ends up open on a deployment that never meant to
    enable one.
    """
    if not configured_token:
        return False
    if not supplied_token:
        return False
    return hmac.compare_digest(str(supplied_token), str(configured_token))


def token_from_headers(headers):
    """Read the admin token from a request.

    A dedicated header rather than Authorization, which already carries a
    player's Supabase token -- overloading it would make it ambiguous which
    credential a request was presenting.
    """
    headers = headers or {}
    return headers.get("X-Admin-Token") or headers.get("x-admin-token")


class AdminOperations:
    """The operations themselves, against a Supabase client."""

    def __init__(self, client, game_slug="journeyman"):
        self._client = client
        self._game_slug = game_slug

    def swap_puzzle(self, puzzle_date, player_id):
        """Point a date at a different player.

        Rewrites the denormalised payload too, because that is what a session
        actually reads -- updating only the reference would change nothing a
        player sees.
        """
        player = (
            self._client.table("players")
            .select("id,name,stints")
            .eq("id", str(player_id))
            .limit(1)
            .execute()
        )
        if not player.data:
            raise AdminError(f"no player with id {player_id!r}")

        row = player.data[0]
        teams = [stint["team"] for stint in row.get("stints") or []]
        if len(set(teams)) < 2:
            raise AdminError(f"{row['name']} has fewer than two distinct franchises")

        self._client.table("puzzles").upsert(
            {
                "game_slug": self._game_slug,
                "puzzle_date": str(puzzle_date),
                "player_id": row["id"],
                "payload": {
                    "player_id": row["id"],
                    "player_name": row["name"],
                    "teams": teams,
                },
            },
            on_conflict="game_slug,puzzle_date",
        ).execute()

        return {"puzzle_date": str(puzzle_date), "player": row["name"], "teams": teams}

    def void_day(self, puzzle_date, reason=None):
        """Stop a day's results counting. Reversible."""
        response = self._client.rpc(
            "set_day_voided",
            {
                "p_game_slug": self._game_slug,
                "p_puzzle_date": str(puzzle_date),
                "p_voided": True,
                "p_reason": reason,
            },
        ).execute()
        return {"puzzle_date": str(puzzle_date), "voided": response.data or 0}

    def restore_day(self, puzzle_date):
        response = self._client.rpc(
            "set_day_voided",
            {
                "p_game_slug": self._game_slug,
                "p_puzzle_date": str(puzzle_date),
                "p_voided": False,
                "p_reason": None,
            },
        ).execute()
        return {"puzzle_date": str(puzzle_date), "restored": response.data or 0}

    def upcoming_puzzles(self, start, days=7):
        """What is scheduled, so a swap can be aimed at the right date."""
        from datetime import timedelta

        end = start + timedelta(days=days - 1)
        response = (
            self._client.table("puzzles")
            .select("puzzle_date,player_id,payload")
            .eq("game_slug", self._game_slug)
            .gte("puzzle_date", str(start))
            .lte("puzzle_date", str(end))
            .order("puzzle_date")
            .execute()
        )
        return [
            {
                "puzzle_date": row["puzzle_date"],
                "player": (row.get("payload") or {}).get("player_name"),
                "num_teams": len((row.get("payload") or {}).get("teams") or []),
            }
            for row in (response.data or [])
        ]
