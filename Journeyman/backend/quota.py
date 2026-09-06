"""Five free unlimited games a day.

A product rule about durable state, which is what makes it different from the
rate limiter next door even though the two look alike. The limiter is about
abuse and may be approximate -- its worst case is somebody getting 2x across a
window boundary, which costs nothing. This is about money, so a sixth free game
handed out because two requests raced is a bug someone can farm. Hence one
atomic statement, in Postgres, not anywhere evictable.

## What it counts

Unlimited mode only. The daily puzzle is free forever and needs no account: it
is the acquisition funnel and the share loop, and a wall in front of it would be
the most expensive possible place to put one.

## Entitlements

Consumed here, owned by entitlements.py. This module asks one question -- is
this caller exempt -- and knows nothing about what was bought or from whom.
That separation is what lets a payment provider change without this file
moving.

## Failing open, and why this one does not

The rate limiter fails open: a limiter that is itself down must not take the
game down. This does the same, and the reasoning is genuinely different rather
than copied. If the quota store is unreachable the choice is to give away some
free games or to stop the game working. Free games are recoverable and an
outage is not, so it fails open too -- but it says so loudly in the log,
because silently free forever is a different problem.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

# Five, not ten. A cap can be loosened later and read as generosity; tightening
# one reads as a takeaway, and the people it annoys are the ones who play most.
FREE_GAMES_PER_DAY = 5

# Unlimited mode only. Named rather than inlined so the one place that decides
# what is chargeable is greppable.
METERED_MODES = frozenset({"unlimited"})


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    used: int
    remaining: int
    limit: int = FREE_GAMES_PER_DAY
    # True when the caller is not on the free tier at all, so the UI can say
    # "unlimited" rather than a misleading "5 left" that never goes down.
    unmetered: bool = False

    @property
    def exhausted(self) -> bool:
        return not self.allowed and not self.unmetered


UNMETERED = QuotaDecision(allowed=True, used=0, remaining=0, unmetered=True)


class QuotaStore(ABC):
    @abstractmethod
    def consume(self, subject, quota_date, limit) -> QuotaDecision:
        """Spend one game and say whether it was allowed."""

    @abstractmethod
    def used(self, subject, quota_date) -> int:
        """How many have been spent, without spending one."""


class InMemoryQuotaStore(QuotaStore):
    """For tests and local runs without a database.

    Not usable in production: each serverless invocation gets its own dict, so
    the allowance would reset whenever a new instance served the request.
    """

    def __init__(self):
        self._used = {}

    def consume(self, subject, quota_date, limit) -> QuotaDecision:
        key = (subject, quota_date)
        used = self._used.get(key, 0) + 1
        self._used[key] = used
        return QuotaDecision(
            allowed=used <= limit,
            used=used,
            remaining=max(limit - used, 0),
            limit=limit,
        )

    def used(self, subject, quota_date) -> int:
        return self._used.get((subject, quota_date), 0)


class PostgresQuotaStore(QuotaStore):
    """Counts in Postgres, atomically. See migration 0012."""

    def __init__(self, client, game_slug="journeyman"):
        self._client = client
        self._game_slug = game_slug

    def consume(self, subject, quota_date, limit) -> QuotaDecision:
        response = self._client.rpc(
            "consume_quota",
            {
                "p_game_slug": self._game_slug,
                "p_subject": subject,
                "p_quota_date": str(quota_date),
                "p_limit": limit,
            },
        ).execute()
        row = (response.data or [{}])[0]
        return QuotaDecision(
            allowed=bool(row.get("allowed")),
            used=int(row.get("used") or 0),
            remaining=int(row.get("remaining") or 0),
            limit=limit,
        )

    def used(self, subject, quota_date) -> int:
        response = self._client.rpc(
            "quota_used",
            {
                "p_game_slug": self._game_slug,
                "p_subject": subject,
                "p_quota_date": str(quota_date),
            },
        ).execute()
        return int(response.data or 0)


def quota_subject(user_id, headers=None):
    """Who this allowance belongs to.

    A signed-in player is keyed on their verified user id. Everyone else is
    keyed on a hash of their address -- because a quota keyed only on accounts
    is bypassed by signing out, which would make it decorative.

    The address handle is deliberately coarse and is the honest ceiling here: a
    shared network shares an allowance, and a new address is a new one. That is
    the cost of letting people play without an account, which is a deliberate
    product choice rather than an oversight.
    """
    if user_id:
        return f"user:{user_id}"

    # Imported here rather than at module scope to keep the one implementation
    # of "how do we identify an anonymous caller" in rate_limit, where it is
    # already tested, without making these two modules circular.
    from rate_limit import hash_client_address

    return f"ip:{hash_client_address(headers or {})}"


def is_metered(mode) -> bool:
    return mode in METERED_MODES


def consume(store, entitlements, mode, user_id, quota_date, headers=None, limit=None):
    """Spend one game if this one is chargeable. The single entry point.

    Returns a QuotaDecision. Callers check `.allowed`; `.remaining` is what the
    UI shows. A mode that is not metered, or a caller who is not on the free
    tier, comes back UNMETERED without touching the store at all -- so the daily
    puzzle costs no query, which matters because it is the busiest path.
    """
    if not is_metered(mode):
        return UNMETERED

    if user_id and entitlements.is_unlimited(user_id):
        return UNMETERED

    return store.consume(
        quota_subject(user_id, headers),
        quota_date,
        FREE_GAMES_PER_DAY if limit is None else limit,
    )


def remaining(store, entitlements, user_id, quota_date, headers=None, limit=None):
    """What is left, without spending anything.

    For showing the count before a player commits to a game. Deliberately a
    separate call from consume rather than a flag on it: a read that can
    accidentally write is the kind of bug that shows up as players losing games
    they never played.
    """
    if user_id and entitlements.is_unlimited(user_id):
        return UNMETERED

    cap = FREE_GAMES_PER_DAY if limit is None else limit
    used = store.used(quota_subject(user_id, headers), quota_date)
    return QuotaDecision(
        allowed=used < cap,
        used=used,
        remaining=max(cap - used, 0),
        limit=cap,
    )
