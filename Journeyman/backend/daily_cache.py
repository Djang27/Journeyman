"""Caching today's puzzle, which is the same row for every player alive.

Every daily start reads one `puzzles` row, and within a day that row is
identical for everyone. At 30k daily players that is 30k round trips to learn
the same three fields. This holds the answer in the process so a warm instance
serves it without touching the database at all.

## Why not "cache at the edge until midnight", as the roadmap said

Two reasons, both worth writing down because the roadmap entry predates Phase 0
and reads plausibly until you try to build it.

**It cannot go at the edge.** The daily is `POST /api/game/start`, and it writes
a session row because the server holds the answer. A POST that mutates state is
not cacheable by any shared cache. The roadmap was describing the pre-Phase-0
`GET /daily-game`, which returned the answer to the browser and held no state --
the same stale assumption that put a client-side result buffer in the fallback
table. What is cacheable is the *lookup inside* the request, which is what this
does.

**"Until midnight" would break the admin swap.** `AdminOperations.swap_puzzle`
exists to fix a bad puzzle in a hurry. A day-long TTL means warm instances keep
serving the old puzzle for up to 24 hours after the swap, and there is no way to
reach into another serverless instance to tell it otherwise. A short TTL is the
honest fix: it bounds how long any instance can be wrong, without needing shared
invalidation.

So the lifetime is the shorter of a small TTL and the time until the date rolls
over. At 60 seconds a day's puzzle costs about 1,440 reads instead of 30,000,
and an operator swapping a puzzle sees it take effect everywhere within a
minute. The remaining 1,440 is not worth a distributed cache and the failure
modes one brings.
"""

from __future__ import annotations

import threading
import time

# Short enough that an admin swap takes effect while someone is still watching,
# long enough that the hot path is not a database call. The bound that matters
# is staleness, not hit rate: going from 60s to an hour would save 1,400 reads a
# day and cost an hour of serving a puzzle an operator already pulled.
DEFAULT_TTL_SECONDS = 60


class PuzzleCache:
    """One puzzle, remembered for a bounded time.

    Holds a single date rather than a map. A puzzle cache with more than one day
    in it is either serving yesterday or prefetching tomorrow, and neither is
    something this needs to do -- so the structure says so.

    Safe to share across threads. The value is treated as immutable; callers get
    the same object back and must not edit it in place.
    """

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS, clock=time.monotonic):
        self._ttl = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._date: str | None = None
        self._value = None
        self._stored_at = 0.0
        self.hits = 0
        self.misses = 0

    def get(self, puzzle_date: str):
        """The cached puzzle for this date, or None.

        A different date is a miss, not a stale hit: that is what makes the
        midnight rollover correct without anyone scheduling anything.
        """
        with self._lock:
            if self._date != puzzle_date or self._value is None:
                self.misses += 1
                return None
            if self._clock() - self._stored_at >= self._ttl:
                # Expired. Drop it rather than leaving it to be re-checked, so
                # a long-idle instance is not holding a day-old puzzle.
                self._date = None
                self._value = None
                self.misses += 1
                return None
            self.hits += 1
            return self._value

    def put(self, puzzle_date: str, value) -> None:
        with self._lock:
            self._date = puzzle_date
            self._value = value
            self._stored_at = self._clock()

    def invalidate(self) -> None:
        """Forget whatever is held.

        Called when this instance is the one that changed the puzzle. It does
        not reach other instances -- the TTL is what covers those.
        """
        with self._lock:
            self._date = None
            self._value = None

    def reset(self) -> None:
        """Forget the puzzle *and* the counters.

        Separate from invalidate() on purpose: an operator swapping a puzzle
        should not also zero the hit rate someone may be reading. This is for
        tests, which need a cache with no history rather than merely no value.
        """
        with self._lock:
            self._date = None
            self._value = None
            self.hits = 0
            self.misses = 0

    def stats(self) -> dict:
        """Hit counts, so the cache can be seen working rather than assumed to.

        `cached_date` being null on a busy deployment means every request is
        missing, which is the symptom of instances being recycled per request.
        """
        with self._lock:
            total = self.hits + self.misses
            return {
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else None,
                "cached_date": self._date,
                "ttl_seconds": self._ttl,
            }
