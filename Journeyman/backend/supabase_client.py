"""Building Supabase clients, in one place.

Every client in the app and in the scheduled jobs is built here, so a bound on
how long a call may take cannot be set in six places and missed in a seventh.
That is not hypothetical: the first timeout fix covered six clients in app.py
and missed the session store -- the one that handles every start and every
guess -- because that client was built inside supabase_store.py instead.

Two policies, because two kinds of caller want opposite things.

The app wants to fail fast. Vercel kills a function long before supabase-py's
120-second default expires, so an unbounded call is a dead function rather than
a handled failure.

A scheduled job wants to be patient and to try again. It runs once a day at a
quiet hour, so its first query regularly lands on a database that has gone
idle, and the gateway can time out before the instance wakes. A short timeout
would only make that fail sooner. What helps is a longer bound and a retry.
"""

from __future__ import annotations

import time

# How long an app request may wait on the database. Generous against a healthy
# query, which runs in well under a second, and short enough to fail before the
# platform kills the function.
DATABASE_TIMEOUT_SECONDS = 5

# The rate limiter gets less. It fails open by design, so waiting on it buys
# nothing: a slow success and a timeout both end with the request allowed.
LIMITER_TIMEOUT_SECONDS = 2

# Scheduled jobs are not racing a function limit, and a cold database can take
# several seconds to answer its first query.
BATCH_TIMEOUT_SECONDS = 30

# Gateway statuses that mean "try again" rather than "you asked for something
# wrong". PostgREST's own error codes are never in here.
TRANSIENT_STATUSES = frozenset({"502", "503", "504"})


def build(config, timeout=DATABASE_TIMEOUT_SECONDS):
    """A Supabase client that gives up in bounded time.

    Does not check that the database is configured; callers already do, and a
    few pass a bare object carrying only the URL and key.
    """
    from supabase.lib.client_options import SyncClientOptions
    from supabase_auth import SyncMemoryStorage

    from supabase import create_client

    return create_client(
        config.supabase_url,
        config.supabase_service_key,
        options=SyncClientOptions(
            postgrest_client_timeout=timeout,
            storage=SyncMemoryStorage(),
        ),
    )


def is_transient(exc) -> bool:
    """Whether a failure is worth retrying.

    A gateway timeout or a dropped connection is. A 400, a 401, a unique
    violation or a permission error is not: retrying those hides a real fault,
    and around a write it can do the write twice.
    """
    import httpx
    from postgrest.exceptions import APIError

    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, APIError):
        return str(exc.code) in TRANSIENT_STATUSES
    return False


def with_retries(fn, attempts=3, base_delay=2.0, sleep=time.sleep):
    """Call fn, retrying transient failures with a growing pause.

    For scheduled jobs only. An app request should fail fast and let the player
    try again; a job nobody is watching should not fail a whole run because its
    first query met a database that was still waking up.

    Only safe around idempotent work. The reconciliation reads it wraps are; a
    write that is not must not go through here.
    """
    attempts = max(1, attempts)
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            if attempt == attempts or not is_transient(exc):
                raise
            sleep(base_delay * attempt)
    raise AssertionError("unreachable")  # pragma: no cover
