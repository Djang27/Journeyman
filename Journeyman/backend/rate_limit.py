"""Application-level rate limiting.

The middle of three layers, and it cannot do the others' jobs:

* A volumetric attack has already cost you by the time this code runs. Only an
  edge -- Cloudflare -- can refuse traffic before it reaches a function.
* The free-tier quota is a product rule about durable state, not a rate limit,
  and belongs with the rest of the game state.

What is left for this layer is the case in between: one caller making far more
requests than a person plays.

Backed by Postgres rather than Redis. The quota above has to be transactional
with session creation, so Postgres is carrying this shape of work regardless,
and a second store would add a secret, a failure mode and something else to
monitor for no benefit at current volume. The interface below is the seam that
makes Redis a swap rather than a rewrite when that changes.
"""

from __future__ import annotations

import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

# Generous enough that nobody playing normally will notice, tight enough that a
# script is stopped well before it costs anything. A game takes at least a few
# seconds to start and a guess takes at least as long to type.
START_LIMIT = (3600, 60)  # 60 games an hour
GUESS_LIMIT = (60, 120)  # 120 guesses a minute

# An IP is personal data and is never stored. The prefix of a salted hash is
# enough to tell two callers apart and useless for identifying either.
IP_HASH_PREFIX = 16


@dataclass(frozen=True)
class Decision:
    allowed: bool
    used: int
    resets_at: float | None = None

    @property
    def retry_after_seconds(self):
        if self.allowed or self.resets_at is None:
            return None
        return max(1, int(self.resets_at - time.time()))


class RateLimiter(ABC):
    @abstractmethod
    def consume(self, bucket, window_seconds, max_requests) -> Decision:
        """Count one request against a bucket and say whether it is allowed."""


class InMemoryRateLimiter(RateLimiter):
    """For tests and single-process local runs.

    Not usable in production: each serverless invocation gets its own dict, so
    the effective limit multiplies by however many instances are warm.
    """

    def __init__(self):
        self._counts = {}

    def consume(self, bucket, window_seconds, max_requests):
        now = time.time()
        window_start = int(now // window_seconds) * window_seconds
        key = (bucket, window_start)
        used = self._counts.get(key, 0) + 1
        self._counts[key] = used
        return Decision(
            allowed=used <= max_requests,
            used=used,
            resets_at=window_start + window_seconds,
        )


class PostgresRateLimiter(RateLimiter):
    """Counts in Postgres, atomically.

    The increment and the decision happen in one statement, so two concurrent
    requests cannot both read the same count and both conclude they are under
    the limit -- the failure a read-then-write version has, which shows up only
    under exactly the load the limiter exists for.
    """

    def __init__(self, client):
        self._client = client

    def consume(self, bucket, window_seconds, max_requests):
        response = self._client.rpc(
            "consume_rate_limit",
            {
                "p_bucket": bucket,
                "p_window_seconds": window_seconds,
                "p_max_requests": max_requests,
            },
        ).execute()

        row = (response.data or [{}])[0]
        resets_at = row.get("resets_at")
        return Decision(
            allowed=bool(row.get("allowed", True)),
            used=int(row.get("used", 0)),
            resets_at=_parse_timestamp(resets_at),
        )


def _parse_timestamp(value):
    if not value:
        return None
    from datetime import datetime

    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()


def caller_bucket(action, user_id, headers=None):
    """Who this request counts against.

    A signed-in player gets their own budget, keyed on the verified user id --
    so sharing an office network does not mean sharing a limit. Everyone else is
    grouped by a hash of their address, which is the only handle available and
    is deliberately coarse.
    """
    if user_id:
        return f"{action}:user:{user_id}"
    return f"{action}:ip:{hash_client_address(headers or {})}"


def hash_client_address(headers):
    """A stable, non-reversible handle for an unauthenticated caller.

    X-Forwarded-For is a list appended to by each proxy; the first entry is the
    original client. It is trivially spoofed, which is accepted: this layer
    raises the cost of abuse rather than making it impossible, and a caller
    willing to forge headers is the edge layer's problem.
    """
    forwarded = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for") or ""
    address = forwarded.split(",")[0].strip() or headers.get("X-Real-IP") or "unknown"
    return hashlib.sha256(address.encode()).hexdigest()[:IP_HASH_PREFIX]


def check(limiter, action, limit, user_id=None, headers=None):
    """Apply a limit, failing open if the limiter itself is unavailable.

    Failing open is deliberate. This is not the security boundary -- identity and
    the curation gate are -- so a limiter outage taking the game down would trade
    a real failure for a hypothetical one. The exception is logged by the caller.
    """
    window_seconds, max_requests = limit
    bucket = caller_bucket(action, user_id, headers)
    return limiter.consume(bucket, window_seconds, max_requests)
